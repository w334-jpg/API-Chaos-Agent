"""Extended tests for PostmanAdapter — covering missing code paths."""

from __future__ import annotations

import json

import pytest

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
from api_chaos_agent.services.postman_adapter import PostmanAdapter


def _v21_collection(**overrides):
    base = {
        "info": {
            "name": "Test",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [],
    }
    base.update(overrides)
    return base


class TestPostmanImportEdgeCases:
    def test_import_from_json_string(self):
        adapter = PostmanAdapter()
        collection = _v21_collection()
        spec = adapter.import_collection(json.dumps(collection))
        assert spec is not None

    def test_import_unsupported_schema_raises(self):
        adapter = PostmanAdapter()
        collection = _v21_collection()
        collection["info"]["schema"] = "https://schema.getpostman.com/json/collection/v1.0/collection.json"
        with pytest.raises(ValueError, match="Unsupported"):
            adapter.import_collection(collection)

    def test_import_nested_folders(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Folder",
                    "item": [
                        {
                            "name": "Get Item",
                            "request": {
                                "method": "GET",
                                "header": [],
                                "url": {"raw": "https://api.example.com/items", "path": ["items"]},
                            },
                            "response": [],
                        }
                    ],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert len(spec.endpoints) == 1

    def test_import_string_url(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Get",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": "https://api.example.com/items",
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert len(spec.endpoints) == 1

    def test_import_url_with_raw_only(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Get",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {"raw": "https://api.example.com/items"},
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert spec.endpoints[0].path == "/items"

    def test_import_non_dict_request_returns_none(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[{"name": "Bad", "request": "not-a-dict"}]
        )
        spec = adapter.import_collection(collection)
        assert len(spec.endpoints) == 0

    def test_import_unknown_method_returns_none(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Bad",
                    "request": {
                        "method": "PROPFIND",
                        "header": [],
                        "url": {"raw": "https://api.example.com/"},
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert len(spec.endpoints) == 0

    def test_import_formdata_body(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Upload",
                    "request": {
                        "method": "POST",
                        "header": [],
                        "body": {
                            "mode": "formdata",
                            "formdata": [
                                {"key": "file", "type": "file", "disabled": False},
                                {"key": "name", "type": "text", "disabled": False},
                            ],
                        },
                        "url": {"raw": "https://api.example.com/upload", "path": ["upload"]},
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert spec.endpoints[0].request_body is not None
        assert spec.endpoints[0].request_body.content_type == "multipart/form-data"

    def test_import_urlencoded_body(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Login",
                    "request": {
                        "method": "POST",
                        "header": [],
                        "body": {
                            "mode": "urlencoded",
                            "urlencoded": [
                                {"key": "username", "value": "admin"},
                                {"key": "password", "value": "secret"},
                            ],
                        },
                        "url": {"raw": "https://api.example.com/login", "path": ["login"]},
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert spec.endpoints[0].request_body is not None
        assert spec.endpoints[0].request_body.content_type == "application/x-www-form-urlencoded"

    def test_import_raw_xml_body(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "XML",
                    "request": {
                        "method": "POST",
                        "header": [],
                        "body": {
                            "mode": "raw",
                            "raw": "<root><item>test</item></root>",
                            "options": {"raw": {"language": "xml"}},
                        },
                        "url": {"raw": "https://api.example.com/data", "path": ["data"]},
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert spec.endpoints[0].request_body.content_type == "application/xml"

    def test_import_raw_text_body(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Text",
                    "request": {
                        "method": "POST",
                        "header": [],
                        "body": {
                            "mode": "raw",
                            "raw": "plain text content",
                            "options": {"raw": {"language": "text"}},
                        },
                        "url": {"raw": "https://api.example.com/data", "path": ["data"]},
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert spec.endpoints[0].request_body.content_type == "text/plain"

    def test_import_raw_json_with_invalid_json(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Bad JSON",
                    "request": {
                        "method": "POST",
                        "header": [],
                        "body": {"mode": "raw", "raw": "not-json"},
                        "url": {"raw": "https://api.example.com/data", "path": ["data"]},
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert spec.endpoints[0].request_body is not None

    def test_import_empty_body_returns_none(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "No Body",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "body": {},
                        "url": {"raw": "https://api.example.com/data", "path": ["data"]},
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert spec.endpoints[0].request_body is None

    def test_import_path_variables(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Get User",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "https://api.example.com/users/1",
                            "path": ["users", "1"],
                            "variable": [{"key": "userId", "value": "1"}],
                        },
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        path_params = [p for p in spec.endpoints[0].parameters if p.location == "path"]
        assert len(path_params) >= 1

    def test_import_header_params(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Get",
                    "request": {
                        "method": "GET",
                        "header": [{"key": "Authorization", "value": "Bearer token", "disabled": False}],
                        "url": {"raw": "https://api.example.com/data", "path": ["data"]},
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        header_params = [p for p in spec.endpoints[0].parameters if p.location == "header"]
        assert len(header_params) >= 1

    def test_import_responses(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Get",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {"raw": "https://api.example.com/data", "path": ["data"]},
                    },
                    "response": [
                        {"name": "Success", "code": 200, "status": "OK"},
                        {"name": "Not Found", "code": "404 Not Found", "status": "Not Found"},
                    ],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert len(spec.endpoints[0].responses) == 2

    def test_import_with_base_url_variable(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            variable=[{"key": "base_url", "value": "https://api.example.com"}]
        )
        spec = adapter.import_collection(collection)
        assert spec.base_url == "https://api.example.com"

    def test_import_with_description(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            info={"name": "T", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json", "description": "A test collection"}
        )
        spec = adapter.import_collection(collection)
        assert spec.description == "A test collection"

    def test_import_url_no_path_segments(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Root",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {"raw": "https://api.example.com"},
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert spec.endpoints[0].path == "/"

    def test_import_non_dict_query_param_skipped(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Get",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "https://api.example.com/data",
                            "path": ["data"],
                            "query": ["not-a-dict"],
                        },
                    },
                    "response": [],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert len(spec.endpoints[0].parameters) == 0

    def test_import_non_dict_response_skipped(self):
        adapter = PostmanAdapter()
        collection = _v21_collection(
            item=[
                {
                    "name": "Get",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {"raw": "https://api.example.com/data", "path": ["data"]},
                    },
                    "response": ["not-a-dict"],
                }
            ]
        )
        spec = adapter.import_collection(collection)
        assert len(spec.endpoints[0].responses) == 0

    def test_infer_fields_from_dict_types(self):
        adapter = PostmanAdapter()
        data = {"name": "test", "age": 30, "active": True, "score": 9.5, "tags": [], "meta": {}}
        fields = adapter._infer_fields_from_dict(data)
        assert len(fields) == 6
        type_map = {f.field_name: f.field_type for f in fields}
        assert type_map["name"] == FieldType.STRING
        assert type_map["age"] == FieldType.INTEGER
        assert type_map["active"] == FieldType.BOOLEAN
        assert type_map["score"] == FieldType.NUMBER
        assert type_map["tags"] == FieldType.ARRAY
        assert type_map["meta"] == FieldType.OBJECT


class TestPostmanExportEdgeCases:
    def test_export_with_base_url(self):
        adapter = PostmanAdapter()
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[Endpoint(path="/test", method=HttpMethod.GET)],
            base_url="https://api.example.com",
        )
        export = adapter.export_collection(spec)
        assert len(export["variable"]) == 1
        assert export["variable"][0]["key"] == "base_url"

    def test_export_json_string(self):
        adapter = PostmanAdapter()
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[Endpoint(path="/test", method=HttpMethod.GET)],
        )
        json_str = adapter.export_collection_json(spec)
        parsed = json.loads(json_str)
        assert "info" in parsed

    def test_export_with_json_body(self):
        adapter = PostmanAdapter()
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[
                Endpoint(
                    path="/users",
                    method=HttpMethod.POST,
                    request_body=RequestBody(
                        content_type="application/json",
                        required=True,
                        fields=[FieldConstraint(field_name="name", field_type=FieldType.STRING)],
                    ),
                )
            ],
        )
        export = adapter.export_collection(spec)
        body = export["item"][0]["request"]["body"]
        assert body["mode"] == "raw"
        assert "json" in body["options"]["raw"]["language"]

    def test_export_with_xml_body(self):
        adapter = PostmanAdapter()
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[
                Endpoint(
                    path="/data",
                    method=HttpMethod.POST,
                    request_body=RequestBody(
                        content_type="application/xml",
                        required=True,
                        fields=[],
                    ),
                )
            ],
        )
        export = adapter.export_collection(spec)
        body = export["item"][0]["request"]["body"]
        assert body["mode"] == "raw"
        assert body["options"]["raw"]["language"] == "xml"

    def test_export_with_formdata_body(self):
        adapter = PostmanAdapter()
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[
                Endpoint(
                    path="/upload",
                    method=HttpMethod.POST,
                    request_body=RequestBody(
                        content_type="multipart/form-data",
                        required=True,
                        fields=[FieldConstraint(field_name="file", field_type=FieldType.STRING)],
                    ),
                )
            ],
        )
        export = adapter.export_collection(spec)
        body = export["item"][0]["request"]["body"]
        assert body["mode"] == "formdata"

    def test_export_with_urlencoded_body(self):
        adapter = PostmanAdapter()
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[
                Endpoint(
                    path="/login",
                    method=HttpMethod.POST,
                    request_body=RequestBody(
                        content_type="application/x-www-form-urlencoded",
                        required=True,
                        fields=[FieldConstraint(field_name="username", field_type=FieldType.STRING)],
                    ),
                )
            ],
        )
        export = adapter.export_collection(spec)
        body = export["item"][0]["request"]["body"]
        assert body["mode"] == "urlencoded"

    def test_export_with_parameters(self):
        adapter = PostmanAdapter()
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[
                Endpoint(
                    path="/users/{id}",
                    method=HttpMethod.GET,
                    parameters=[
                        Parameter(name="id", location="path", param_type=FieldType.STRING, required=True),
                        Parameter(name="q", location="query", param_type=FieldType.STRING, required=False),
                        Parameter(name="Auth", location="header", param_type=FieldType.STRING, required=True),
                    ],
                )
            ],
        )
        export = adapter.export_collection(spec)
        req = export["item"][0]["request"]
        assert len(req["url"]["variable"]) == 1
        assert len(req["url"]["query"]) == 1
        assert len(req["header"]) == 1

    def test_export_with_responses(self):
        adapter = PostmanAdapter()
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[
                Endpoint(
                    path="/test",
                    method=HttpMethod.GET,
                    responses=[ResponseSpec(status_code="200", description="OK")],
                )
            ],
        )
        export = adapter.export_collection(spec)
        assert len(export["item"][0]["response"]) == 1

    def test_export_endpoint_without_summary(self):
        adapter = PostmanAdapter()
        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[Endpoint(path="/test", method=HttpMethod.GET)],
        )
        export = adapter.export_collection(spec)
        assert export["item"][0]["name"] == "GET /test"

    def test_extract_path_from_raw_with_protocol(self):
        adapter = PostmanAdapter()
        path = adapter._extract_path_from_raw("https://api.example.com/v1/users")
        assert path == "/v1/users"

    def test_extract_path_from_raw_no_path(self):
        adapter = PostmanAdapter()
        path = adapter._extract_path_from_raw("https://api.example.com")
        assert path == "/"

    def test_extract_path_from_raw_no_protocol(self):
        adapter = PostmanAdapter()
        path = adapter._extract_path_from_raw("/api/v1/data")
        assert path == "/"

    def test_extract_base_url_found(self):
        variables = [{"key": "base_url", "value": "https://api.example.com"}]
        result = PostmanAdapter._extract_base_url(variables)
        assert result == "https://api.example.com"

    def test_extract_base_url_not_found(self):
        variables = [{"key": "other", "value": "something"}]
        result = PostmanAdapter._extract_base_url(variables)
        assert result is None

    def test_extract_base_url_non_dict_skipped(self):
        variables = ["not-a-dict"]
        result = PostmanAdapter._extract_base_url(variables)
        assert result is None
