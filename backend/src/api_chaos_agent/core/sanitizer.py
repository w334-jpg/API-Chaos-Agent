"""Schema sanitizer - Remove sensitive data before sending to external LLM services.

Strips PII, credentials, internal hostnames, and other sensitive information
from API specifications before they are transmitted to third-party LLM providers.
"""

from __future__ import annotations

import re
from typing import Any

_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
        "x-session-id",
        "proxy-authorization",
        "www-authenticate",
        "x-forwarded-for",
        "x-real-ip",
    }
)

_SENSITIVE_PARAM_PATTERNS = [
    re.compile(
        r"(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)",
        re.IGNORECASE,
    ),
    re.compile(r"(ssn|social[_-]?security|credit[_-]?card|card[_-]?number|cvv|cvc)", re.IGNORECASE),
    re.compile(r"(email|phone|mobile|address|zip|postal)", re.IGNORECASE),
]

_REDACTED = "[REDACTED]"

_HOSTNAME_SANITIZE_PATTERN = re.compile(
    r"(https?://)([a-zA-Z0-9][\w.-]*\.(internal|local|corp|private|lan|intranet|vpn)(?::\d+)?)",
    re.IGNORECASE,
)

_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


class SchemaSanitizer:
    """Sanitize API specifications to remove sensitive data before LLM processing.

    Performs in-place modification of the spec dict to avoid the overhead
    of ``deepcopy`` on large schemas.  Callers that need the original
    untouched should pass a copy themselves.
    """

    def sanitize(self, spec: dict[str, Any]) -> dict[str, Any]:
        self._sanitize_servers(spec)
        self._sanitize_paths(spec)
        self._sanitize_components(spec)
        self._sanitize_security(spec)
        self._sanitize_info(spec)
        return spec

    def _sanitize_servers(self, spec: dict[str, Any]) -> None:
        for server in spec.get("servers", []):
            if isinstance(server, dict):
                url = server.get("url", "")
                server["url"] = self._sanitize_url(url)
                variables = server.get("variables", {})
                if isinstance(variables, dict):
                    for key, var in variables.items():
                        if isinstance(var, dict) and "default" in var:
                            var["default"] = self._sanitize_value(key, var["default"])

    def _sanitize_paths(self, spec: dict[str, Any]) -> None:
        for path_item in spec.get("paths", {}).values():
            if not isinstance(path_item, dict):
                continue
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                self._sanitize_operation(operation)

    def _sanitize_operation(self, operation: dict[str, Any]) -> None:
        for param in operation.get("parameters", []):
            if isinstance(param, dict):
                self._sanitize_parameter(param)

        request_body = operation.get("requestBody")
        if isinstance(request_body, dict):
            self._sanitize_request_body(request_body)

        for resp in operation.get("responses", {}).values():
            if not isinstance(resp, dict):
                continue
            for header_name, header_val in resp.get("headers", {}).items():
                if isinstance(header_val, dict) and self._is_sensitive_header(header_name):
                    if "schema" in header_val and isinstance(header_val["schema"], dict):
                        header_val["schema"]["default"] = _REDACTED
                        header_val["schema"]["example"] = _REDACTED

    def _sanitize_parameter(self, param: dict[str, Any]) -> None:
        name = param.get("name", "")
        if self._is_sensitive_param_name(name):
            schema = param.get("schema", {})
            if isinstance(schema, dict):
                schema["default"] = _REDACTED
                schema["example"] = _REDACTED
                if "enum" in schema:
                    schema["enum"] = [_REDACTED]
            param["description"] = self._redact_description(param.get("description", ""))

    def _sanitize_request_body(self, body: dict[str, Any]) -> None:
        for ct_value in body.get("content", {}).values():
            if not isinstance(ct_value, dict):
                continue
            schema = ct_value.get("schema", {})
            if isinstance(schema, dict):
                self._sanitize_schema(schema)
            example = ct_value.get("example")
            if isinstance(example, dict):
                ct_value["example"] = self._sanitize_example(example)

    def _sanitize_schema(self, schema: dict[str, Any]) -> None:
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for prop_name, prop_schema in properties.items():
                if not isinstance(prop_schema, dict):
                    continue
                if self._is_sensitive_param_name(prop_name):
                    prop_schema["default"] = _REDACTED
                    prop_schema["example"] = _REDACTED
                    if "enum" in prop_schema:
                        prop_schema["enum"] = [_REDACTED]
                if "properties" in prop_schema:
                    self._sanitize_schema(prop_schema)

        items = schema.get("items")
        if isinstance(items, dict):
            self._sanitize_schema(items)

    def _sanitize_components(self, spec: dict[str, Any]) -> None:
        components = spec.get("components", {})
        security_schemes = components.get("securitySchemes", {})
        if isinstance(security_schemes, dict):
            for scheme in security_schemes.values():
                if isinstance(scheme, dict):
                    if "x-tokenUrl" in scheme:
                        scheme["x-tokenUrl"] = _REDACTED
                    if scheme.get("type") in ("http",) and scheme.get("scheme") in (
                        "basic",
                        "bearer",
                    ):
                        scheme["description"] = _REDACTED

        for schema_def in components.get("schemas", {}).values():
            if isinstance(schema_def, dict):
                self._sanitize_schema(schema_def)

    def _sanitize_security(self, spec: dict[str, Any]) -> None:
        security = spec.get("security", [])
        if isinstance(security, list):
            for sec_req in security:
                if isinstance(sec_req, dict):
                    for scheme_name, scopes in sec_req.items():
                        sec_req[scheme_name] = [_REDACTED if s else s for s in (scopes or [])]

    def _sanitize_info(self, spec: dict[str, Any]) -> None:
        contact = spec.get("info", {}).get("contact", {})
        if isinstance(contact, dict):
            if "email" in contact:
                contact["email"] = _REDACTED
            if "name" in contact:
                contact["name"] = _REDACTED

    def _sanitize_url(self, url: str) -> str:
        url = _HOSTNAME_SANITIZE_PATTERN.sub(r"\1[sanitized-host]", url)
        url = _IP_PATTERN.sub("[sanitized-ip]", url)
        return url

    def _sanitize_value(self, key: str, value: Any) -> Any:
        if isinstance(value, str) and self._is_sensitive_param_name(key):
            return _REDACTED
        if isinstance(value, str):
            return self._sanitize_url(value)
        return value

    def _sanitize_example(self, example: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in example.items():
            if self._is_sensitive_param_name(key):
                result[key] = _REDACTED
            elif isinstance(value, dict):
                result[key] = self._sanitize_example(value)
            elif isinstance(value, str):
                result[key] = self._sanitize_url(value)
            else:
                result[key] = value
        return result

    def _redact_description(self, description: str) -> str:
        for pattern in _SENSITIVE_PARAM_PATTERNS:
            if pattern.search(description):
                return _REDACTED
        return description

    @staticmethod
    def _is_sensitive_header(name: str) -> bool:
        return name.lower().replace("-", "").replace("_", "") in {
            h.replace("-", "").replace("_", "") for h in _SENSITIVE_HEADER_NAMES
        }

    @staticmethod
    def _is_sensitive_param_name(name: str) -> bool:
        lower_name = name.lower()
        for pattern in _SENSITIVE_PARAM_PATTERNS:
            if pattern.search(lower_name):
                return True
        return False


sanitizer = SchemaSanitizer()
