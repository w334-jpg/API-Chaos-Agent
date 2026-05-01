"""SchemaParser - Parse OpenAPI 3.0 specs (JSON/YAML) into structured APISpec models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from prance import ResolvingParser

from api_chaos_agent.core.logging import get_logger
from api_chaos_agent.models.schema import (
    APISpec,
    Endpoint,
    FieldConstraint,
    FieldType,
    HttpMethod,
    Parameter,
    RequestBody,
    ResponseSpec,
)

_METHOD_MAP: dict[str, HttpMethod] = {
    "get": HttpMethod.GET,
    "post": HttpMethod.POST,
    "put": HttpMethod.PUT,
    "patch": HttpMethod.PATCH,
    "delete": HttpMethod.DELETE,
    "head": HttpMethod.HEAD,
    "options": HttpMethod.OPTIONS,
}

_TYPE_MAP: dict[str, FieldType] = {
    "string": FieldType.STRING,
    "integer": FieldType.INTEGER,
    "number": FieldType.NUMBER,
    "boolean": FieldType.BOOLEAN,
    "array": FieldType.ARRAY,
    "object": FieldType.OBJECT,
    "null": FieldType.NULL,
}


class SchemaParser:
    """Parse OpenAPI 3.0 specification files into structured APISpec objects."""

    _logger = get_logger(__name__)

    def parse(self, file_path: str) -> APISpec:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenAPI spec file not found: {file_path}")

        suffix = path.suffix.lower()
        if suffix not in (".json", ".yaml", ".yml"):
            raise ValueError(
                f"Unsupported file extension '{suffix}'. Only .json, .yaml, .yml are supported."
            )

        raw_text = path.read_text(encoding="utf-8")
        try:
            if suffix == ".json":
                raw_spec = json.loads(raw_text)
            else:
                raw_spec = yaml.safe_load(raw_text)
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise ValueError(f"Failed to parse file '{file_path}': {exc}") from exc

        if not isinstance(raw_spec, dict):
            raise ValueError(f"Invalid OpenAPI spec: expected a mapping, got {type(raw_spec).__name__}")
        if "openapi" not in raw_spec:
            raise ValueError("Invalid OpenAPI spec: missing 'openapi' version field.")

        spec: dict[str, Any] = raw_spec
        try:
            resolved_parser = ResolvingParser(str(path), backend="openapi-spec-validator")
            spec = resolved_parser.specification
        except Exception as exc:
            self._logger.warning("schema_ref_resolution_failed", file=file_path, error=str(exc))

        info = spec.get("info", {})
        title = info.get("title", "")
        version = info.get("version", "")
        description = info.get("description", "")

        base_url = self._extract_base_url(spec)

        raw_paths = raw_spec.get("paths", {})
        endpoints = self.extract_endpoints(spec, raw_paths)

        return APISpec(
            title=title,
            version=version,
            description=description,
            endpoints=endpoints,
            base_url=base_url,
            raw_spec=raw_spec,
        )

    def extract_endpoints(self, spec: dict, raw_paths: dict | None = None) -> list[Endpoint]:
        endpoints: list[Endpoint] = []
        paths = spec.get("paths", {})
        components = spec.get("components", {})
        if raw_paths is None:
            raw_paths = paths

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            raw_path_item = raw_paths.get(path, {})
            if not isinstance(raw_path_item, dict):
                raw_path_item = {}

            for method_lower, operation in path_item.items():
                method = _METHOD_MAP.get(method_lower)
                if method is None:
                    continue
                if not isinstance(operation, dict):
                    continue

                parameters = self._parse_parameters(
                    path_item.get("parameters", []) + operation.get("parameters", [])
                )

                request_body = self._parse_request_body(
                    operation.get("requestBody"), components
                )

                raw_operation = raw_path_item.get(method_lower, {})
                raw_responses = raw_operation.get("responses", {}) if isinstance(raw_operation, dict) else {}
                responses = self._parse_responses(operation.get("responses", {}), raw_responses)

                endpoint = Endpoint(
                    path=path,
                    method=method,
                    summary=operation.get("summary", ""),
                    description=operation.get("description", ""),
                    parameters=parameters,
                    request_body=request_body,
                    responses=responses,
                    tags=operation.get("tags", []),
                    operation_id=operation.get("operationId"),
                )
                endpoints.append(endpoint)

        return endpoints

    def infer_types(self, schema: dict) -> list[FieldConstraint]:
        if not schema:
            return []

        schema_type = schema.get("type")
        properties = schema.get("properties")

        if properties:
            required_fields = set(schema.get("required", []))
            fields: list[FieldConstraint] = []
            for prop_name, prop_schema in properties.items():
                if not isinstance(prop_schema, dict):
                    continue
                field = self._build_field_constraint(prop_name, prop_schema, prop_name in required_fields)
                fields.append(field)
            return fields

        if schema_type:
            field_type = _TYPE_MAP.get(schema_type, FieldType.STRING)
            field = FieldConstraint(
                field_name="",
                field_type=field_type,
                min_length=schema.get("minLength"),
                max_length=schema.get("maxLength"),
                minimum=schema.get("minimum"),
                maximum=schema.get("maximum"),
                pattern=schema.get("pattern"),
                format=schema.get("format"),
                enum_values=schema.get("enum"),
                default=schema.get("default"),
            )
            return [field]

        return []

    def _parse_parameters(self, parameters: list[dict]) -> list[Parameter]:
        result: list[Parameter] = []
        for param in parameters:
            if not isinstance(param, dict):
                continue
            schema = param.get("schema", {})
            param_type = _TYPE_MAP.get(schema.get("type", "string"), FieldType.STRING)
            constraints = self.infer_types(schema) if schema else []

            parameter = Parameter(
                name=param.get("name", ""),
                location=param.get("in", "query"),
                param_type=param_type,
                required=param.get("required", False),
                description=param.get("description", ""),
                constraints=constraints,
            )
            result.append(parameter)
        return result

    def _parse_request_body(self, request_body: dict | None, components: dict) -> RequestBody | None:
        if not request_body:
            return None

        content = request_body.get("content", {})
        required = request_body.get("required", False)

        content_type = "application/json"
        schema: dict[str, Any] = {}

        if content:
            for ct, ct_value in content.items():
                content_type = ct
                schema = ct_value.get("schema", {})
                break

        if "$ref" in schema:
            ref_path = schema["$ref"]
            resolved = self._resolve_ref(ref_path, components)
            if resolved:
                schema = resolved

        fields = self.infer_types(schema)

        return RequestBody(
            content_type=content_type,
            required=required,
            fields=fields,
            raw_schema=schema,
        )

    def _resolve_ref(self, ref: str, components: dict) -> dict:
        if not ref.startswith("#/"):
            return {}

        parts = ref[2:].split("/")
        current: Any = components
        for part in parts:
            if part == "components":
                continue
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return {}

        return current if isinstance(current, dict) else {}

    @staticmethod
    def _extract_base_url(spec: dict) -> str | None:
        servers = spec.get("servers", [])
        if servers and isinstance(servers, list) and len(servers) > 0:
            url = servers[0].get("url")
            if url:
                return url
        return None

    @staticmethod
    def _parse_responses(responses: dict, raw_responses: dict | None = None) -> list[ResponseSpec]:
        if raw_responses is None:
            raw_responses = responses
        result: list[ResponseSpec] = []
        for status_code, response in responses.items():
            if not isinstance(response, dict):
                continue
            description = response.get("description", "")
            content = response.get("content", {})
            content_type: str | None = None
            schema_ref: str | None = None

            raw_response = raw_responses.get(status_code, {})
            if isinstance(raw_response, dict):
                raw_content = raw_response.get("content", {})
                if raw_content:
                    for ct, ct_value in raw_content.items():
                        if isinstance(ct_value, dict):
                            raw_schema = ct_value.get("schema", {})
                            if "$ref" in raw_schema:
                                schema_ref = raw_schema["$ref"]
                            elif "items" in raw_schema and isinstance(raw_schema["items"], dict):
                                items_ref = raw_schema["items"].get("$ref")
                                if items_ref:
                                    schema_ref = items_ref

            if content:
                for ct, ct_value in content.items():
                    content_type = ct
                    if schema_ref is None:
                        schema = ct_value.get("schema", {})
                        if "$ref" in schema:
                            schema_ref = schema["$ref"]
                        elif "items" in schema and isinstance(schema["items"], dict):
                            items_ref = schema["items"].get("$ref")
                            if items_ref:
                                schema_ref = items_ref
                    break

            result.append(
                ResponseSpec(
                    status_code=status_code,
                    description=description,
                    content_type=content_type,
                    schema_ref=schema_ref,
                )
            )
        return result

    @staticmethod
    def _build_field_constraint(name: str, schema: dict, required: bool = False) -> FieldConstraint:
        field_type = _TYPE_MAP.get(schema.get("type", "string"), FieldType.STRING)
        return FieldConstraint(
            field_name=name,
            field_type=field_type,
            required=required,
            min_length=schema.get("minLength"),
            max_length=schema.get("maxLength"),
            minimum=schema.get("minimum"),
            maximum=schema.get("maximum"),
            pattern=schema.get("pattern"),
            format=schema.get("format"),
            enum_values=schema.get("enum"),
            default=schema.get("default"),
        )
