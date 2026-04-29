"""Postman Collection v2.1 import/export adapter.

Converts between Postman Collection v2.1 format and internal APISpec models,
enabling seamless interoperability with Postman workflows.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

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
    "GET": HttpMethod.GET,
    "POST": HttpMethod.POST,
    "PUT": HttpMethod.PUT,
    "PATCH": HttpMethod.PATCH,
    "DELETE": HttpMethod.DELETE,
    "HEAD": HttpMethod.HEAD,
    "OPTIONS": HttpMethod.OPTIONS,
}

_METHOD_REVERSE: dict[HttpMethod, str] = {v: k for k, v in _METHOD_MAP.items()}

_TYPE_MAP: dict[str, FieldType] = {
    "string": FieldType.STRING,
    "integer": FieldType.INTEGER,
    "number": FieldType.NUMBER,
    "boolean": FieldType.BOOLEAN,
    "array": FieldType.ARRAY,
    "object": FieldType.OBJECT,
    "null": FieldType.NULL,
}


class PostmanAdapter:
    """Adapter for importing and exporting Postman Collection v2.1 format."""

    def import_collection(self, data: str | dict) -> APISpec:
        if isinstance(data, str):
            raw = json.loads(data)
        else:
            raw = data

        info = raw.get("info", {})
        title = info.get("name", "Imported Collection")
        description = info.get("description", "")
        schema_version = info.get("schema", "")

        if not schema_version.startswith("https://schema.getpostman.com/json/collection/v2.1"):
            raise ValueError(
                f"Unsupported Postman Collection schema: {schema_version}. "
                "Only v2.1 is supported."
            )

        items = raw.get("item", [])
        endpoints = self._flatten_items(items)

        variables = raw.get("variable", [])
        base_url = self._extract_base_url(variables)

        return APISpec(
            title=title,
            version="2.1.0",
            description=description or "",
            endpoints=endpoints,
            base_url=base_url,
            raw_spec=raw,
        )

    def export_collection(self, spec: APISpec) -> dict[str, Any]:
        items: list[dict[str, Any]] = []

        for endpoint in spec.endpoints:
            item = self._endpoint_to_item(endpoint, spec.base_url)
            items.append(item)

        collection_id = str(uuid.uuid4())

        variables = []
        if spec.base_url:
            variables.append({
                "key": "base_url",
                "value": spec.base_url,
                "type": "string",
            })

        return {
            "info": {
                "_postman_id": collection_id,
                "name": spec.title,
                "description": spec.description or "",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": items,
            "variable": variables,
        }

    def export_collection_json(self, spec: APISpec, indent: int = 2) -> str:
        collection = self.export_collection(spec)
        return json.dumps(collection, indent=indent, ensure_ascii=False)

    def _flatten_items(self, items: list[dict]) -> list[Endpoint]:
        endpoints: list[Endpoint] = []
        for item in items:
            if "item" in item and isinstance(item["item"], list):
                endpoints.extend(self._flatten_items(item["item"]))
            elif "request" in item:
                endpoint = self._parse_request(item)
                if endpoint:
                    endpoints.append(endpoint)
        return endpoints

    def _parse_request(self, item: dict) -> Endpoint | None:
        request = item.get("request", {})
        if not isinstance(request, dict):
            return None

        method_str = request.get("method", "GET").upper()
        method = _METHOD_MAP.get(method_str)
        if method is None:
            return None

        url_obj = request.get("url", {})
        if isinstance(url_obj, str):
            path = url_obj
        elif isinstance(url_obj, dict):
            raw_path = url_obj.get("raw", "")
            path_segments = url_obj.get("path", [])
            if path_segments:
                path = "/" + "/".join(str(s) for s in path_segments)
            else:
                path = self._extract_path_from_raw(raw_path)
        else:
            path = "/"

        parameters = self._parse_postman_params(request)
        request_body = self._parse_postman_body(request)
        responses = self._parse_postman_responses(item)

        return Endpoint(
            path=path,
            method=method,
            summary=item.get("name", ""),
            description=request.get("description", ""),
            parameters=parameters,
            request_body=request_body,
            responses=responses,
            tags=[],
        )

    def _extract_path_from_raw(self, raw_url: str) -> str:
        if "://" in raw_url:
            _, rest = raw_url.split("://", 1)
            if "/" in rest:
                return "/" + rest.split("/", 1)[1]
        return "/"

    def _parse_postman_params(self, request: dict) -> list[Parameter]:
        params: list[Parameter] = []
        for param in request.get("url", {}).get("query", []) or []:
            if not isinstance(param, dict):
                continue
            params.append(Parameter(
                name=param.get("key", ""),
                location="query",
                param_type=FieldType.STRING,
                required=param.get("disabled", True) is False,
                description=param.get("description", ""),
            ))
        for param in request.get("url", {}).get("variable", []) or []:
            if not isinstance(param, dict):
                continue
            params.append(Parameter(
                name=param.get("key", ""),
                location="path",
                param_type=FieldType.STRING,
                required=True,
                description=param.get("description", ""),
            ))
        for header in request.get("header", []) or []:
            if not isinstance(header, dict):
                continue
            params.append(Parameter(
                name=header.get("key", ""),
                location="header",
                param_type=FieldType.STRING,
                required=header.get("disabled", True) is False,
                description=header.get("description", ""),
            ))
        return params

    def _parse_postman_body(self, request: dict) -> RequestBody | None:
        body = request.get("body", {})
        if not body or not isinstance(body, dict):
            return None

        mode = body.get("mode", "")
        if mode == "raw":
            content_type = "application/json"
            options = body.get("options", {})
            if isinstance(options, dict) and "raw" in options:
                lang = options["raw"].get("language", "json")
                if lang == "xml":
                    content_type = "application/xml"
                elif lang == "text":
                    content_type = "text/plain"

            raw_text = body.get("raw", "")
            fields: list[FieldConstraint] = []
            try:
                parsed = json.loads(raw_text)
                if isinstance(parsed, dict):
                    fields = self._infer_fields_from_dict(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

            return RequestBody(
                content_type=content_type,
                required=True,
                fields=fields,
                raw_schema={"type": "object"} if fields else {},
            )

        if mode == "formdata":
            fields = []
            for entry in body.get("formdata", []) or []:
                if isinstance(entry, dict):
                    fields.append(FieldConstraint(
                        field_name=entry.get("key", ""),
                        field_type=FieldType.STRING,
                        required=entry.get("type", "text") != "text" or not entry.get("disabled", False),
                    ))
            return RequestBody(
                content_type="multipart/form-data",
                required=True,
                fields=fields,
                raw_schema={"type": "object"},
            )

        if mode == "urlencoded":
            fields = []
            for entry in body.get("urlencoded", []) or []:
                if isinstance(entry, dict):
                    fields.append(FieldConstraint(
                        field_name=entry.get("key", ""),
                        field_type=FieldType.STRING,
                    ))
            return RequestBody(
                content_type="application/x-www-form-urlencoded",
                required=True,
                fields=fields,
                raw_schema={"type": "object"},
            )

        return None

    def _infer_fields_from_dict(self, data: dict) -> list[FieldConstraint]:
        fields: list[FieldConstraint] = []
        for key, value in data.items():
            if isinstance(value, str):
                ft = FieldType.STRING
            elif isinstance(value, bool):
                ft = FieldType.BOOLEAN
            elif isinstance(value, int):
                ft = FieldType.INTEGER
            elif isinstance(value, float):
                ft = FieldType.NUMBER
            elif isinstance(value, list):
                ft = FieldType.ARRAY
            elif isinstance(value, dict):
                ft = FieldType.OBJECT
            else:
                ft = FieldType.STRING
            fields.append(FieldConstraint(field_name=key, field_type=ft))
        return fields

    def _parse_postman_responses(self, item: dict) -> list[ResponseSpec]:
        responses: list[ResponseSpec] = []
        for resp in item.get("response", []) or []:
            if not isinstance(resp, dict):
                continue
            code = resp.get("code", "200")
            if isinstance(code, int):
                status_code = str(code)
            else:
                status_code = str(code).split()[0] if str(code) else "200"

            responses.append(ResponseSpec(
                status_code=status_code,
                description=resp.get("name", ""),
                content_type="application/json",
            ))
        return responses

    def _endpoint_to_item(self, endpoint: Endpoint, base_url: str | None) -> dict[str, Any]:
        url = f"{{{{base_url}}}}{endpoint.path}" if base_url else endpoint.path

        query_params = [
            {
                "key": p.name,
                "value": "",
                "disabled": not p.required,
                "description": p.description,
            }
            for p in endpoint.parameters
            if p.location == "query"
        ]

        path_vars = [
            {
                "key": p.name,
                "value": "",
                "description": p.description,
            }
            for p in endpoint.parameters
            if p.location == "path"
        ]

        headers = [
            {
                "key": p.name,
                "value": "",
                "disabled": not p.required,
                "description": p.description,
            }
            for p in endpoint.parameters
            if p.location == "header"
        ]

        body: dict[str, Any] | None = None
        if endpoint.request_body:
            ct = endpoint.request_body.content_type
            if "json" in ct:
                body = {
                    "mode": "raw",
                    "raw": json.dumps(
                        {f.field_name: f.default or "" for f in endpoint.request_body.fields},
                        indent=2,
                    ),
                    "options": {"raw": {"language": "json"}},
                }
            elif "xml" in ct:
                body = {
                    "mode": "raw",
                    "raw": "<root></root>",
                    "options": {"raw": {"language": "xml"}},
                }
            elif "form-data" in ct:
                body = {
                    "mode": "formdata",
                    "formdata": [
                        {"key": f.field_name, "value": str(f.default or ""), "type": "text"}
                        for f in endpoint.request_body.fields
                    ],
                }
            elif "urlencoded" in ct:
                body = {
                    "mode": "urlencoded",
                    "urlencoded": [
                        {"key": f.field_name, "value": str(f.default or ""), "type": "text"}
                        for f in endpoint.request_body.fields
                    ],
                }

        responses = []
        for resp in endpoint.responses:
            responses.append({
                "name": resp.description or f"Status {resp.status_code}",
                "code": int(resp.status_code) if resp.status_code.isdigit() else 200,
                "status": resp.description or "OK",
                "_postman_previewlanguage": "json",
            })

        return {
            "name": endpoint.summary or f"{_METHOD_REVERSE.get(endpoint.method, 'GET')} {endpoint.path}",
            "request": {
                "method": _METHOD_REVERSE.get(endpoint.method, "GET"),
                "header": headers,
                "body": body,
                "url": {
                    "raw": url,
                    "host": ["{{base_url}}"] if base_url else ["localhost"],
                    "path": [s for s in endpoint.path.split("/") if s],
                    "query": query_params,
                    "variable": path_vars,
                },
                "description": endpoint.description,
            },
            "response": responses,
        }

    @staticmethod
    def _extract_base_url(variables: list[dict]) -> str | None:
        for var in variables:
            if isinstance(var, dict) and var.get("key") == "base_url":
                return var.get("value")
        return None
