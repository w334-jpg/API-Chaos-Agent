"""Tests for SchemaParser - TDD Step 1: Write tests FIRST."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

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
from api_chaos_agent.services.schema_parser import SchemaParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PETSTORE_JSON = FIXTURES_DIR / "petstore_openapi.json"
PETSTORE_YAML = FIXTURES_DIR / "petstore_openapi.yaml"


# ---------------------------------------------------------------------------
# 1. Test parsing a valid OpenAPI 3.0 JSON file
# ---------------------------------------------------------------------------
class TestParseValidJSON:
    def test_parse_json_returns_api_spec(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        assert isinstance(result, APISpec)

    def test_parse_json_extracts_title(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        assert result.title == "Petstore API"

    def test_parse_json_extracts_version(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        assert result.version == "1.0.0"

    def test_parse_json_extracts_description(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        assert result.description == "A sample API for pet store"

    def test_parse_json_populates_raw_spec(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        assert isinstance(result.raw_spec, dict)
        assert "openapi" in result.raw_spec


# ---------------------------------------------------------------------------
# 2. Test parsing a valid OpenAPI 3.0 YAML file
# ---------------------------------------------------------------------------
class TestParseValidYAML:
    def test_parse_yaml_returns_api_spec(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_YAML))
        assert isinstance(result, APISpec)

    def test_parse_yaml_extracts_title(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        assert result.title == "Petstore API"

    def test_parse_yaml_extracts_version(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_YAML))
        assert result.version == "1.0.0"

    def test_parse_yaml_extracts_description(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_YAML))
        assert result.description == "A sample API in YAML format"


# ---------------------------------------------------------------------------
# 3. Test extracting endpoints from parsed spec
# ---------------------------------------------------------------------------
class TestExtractEndpoints:
    def test_json_has_correct_endpoint_count(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        # GET /pets, POST /pets, GET /pets/{petId}, DELETE /pets/{petId}
        assert len(result.endpoints) == 4

    def test_yaml_has_correct_endpoint_count(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_YAML))
        # GET /users, POST /users
        assert len(result.endpoints) == 2

    def test_endpoint_has_path(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        paths = {e.path for e in result.endpoints}
        assert "/pets" in paths
        assert "/pets/{petId}" in paths

    def test_endpoint_has_method(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        methods_by_path: dict[str, list[HttpMethod]] = {}
        for e in result.endpoints:
            methods_by_path.setdefault(e.path, []).append(e.method)
        assert HttpMethod.GET in methods_by_path["/pets"]
        assert HttpMethod.POST in methods_by_path["/pets"]
        assert HttpMethod.GET in methods_by_path["/pets/{petId}"]
        assert HttpMethod.DELETE in methods_by_path["/pets/{petId}"]

    def test_endpoint_has_summary(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        assert len(get_pets) == 1
        assert get_pets[0].summary == "List all pets"

    def test_endpoint_has_operation_id(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        assert get_pets[0].operation_id == "listPets"

    def test_endpoint_has_tags(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        assert "pets" in get_pets[0].tags

    def test_endpoint_has_parameters(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        assert len(get_pets[0].parameters) >= 1
        limit_param = [p for p in get_pets[0].parameters if p.name == "limit"]
        assert len(limit_param) == 1
        assert limit_param[0].location == "query"
        assert limit_param[0].param_type == FieldType.INTEGER
        assert limit_param[0].required is False

    def test_path_parameter_is_required(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pet = [e for e in result.endpoints if e.path == "/pets/{petId}" and e.method == HttpMethod.GET]
        pet_id_param = [p for p in get_pet[0].parameters if p.name == "petId"]
        assert len(pet_id_param) == 1
        assert pet_id_param[0].required is True
        assert pet_id_param[0].location == "path"


# ---------------------------------------------------------------------------
# 4. Test inferring field types from JSON Schema
# ---------------------------------------------------------------------------
class TestInferTypes:
    def test_string_type(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "string"})
        assert len(result) == 1
        assert result[0].field_type == FieldType.STRING

    def test_integer_type(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "integer"})
        assert len(result) == 1
        assert result[0].field_type == FieldType.INTEGER

    def test_number_type(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "number"})
        assert len(result) == 1
        assert result[0].field_type == FieldType.NUMBER

    def test_boolean_type(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "boolean"})
        assert len(result) == 1
        assert result[0].field_type == FieldType.BOOLEAN

    def test_array_type(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "array", "items": {"type": "string"}})
        assert len(result) == 1
        assert result[0].field_type == FieldType.ARRAY

    def test_object_type_with_properties(self):
        parser = SchemaParser()
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }
        result = parser.infer_types(schema)
        # Should produce fields for each property
        field_names = {f.field_name for f in result}
        assert "name" in field_names
        assert "age" in field_names

    def test_object_type_without_properties(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "object"})
        assert len(result) == 1
        assert result[0].field_type == FieldType.OBJECT

    def test_required_fields_marked(self):
        parser = SchemaParser()
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "tag": {"type": "string"},
            },
        }
        result = parser.infer_types(schema)
        name_field = [f for f in result if f.field_name == "name"][0]
        tag_field = [f for f in result if f.field_name == "tag"][0]
        assert name_field.required is True
        assert tag_field.required is False


# ---------------------------------------------------------------------------
# 5. Test extracting field constraints
# ---------------------------------------------------------------------------
class TestFieldConstraints:
    def test_min_length(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "string", "minLength": 1})
        assert result[0].min_length == 1

    def test_max_length(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "string", "maxLength": 100})
        assert result[0].max_length == 100

    def test_minimum(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "integer", "minimum": 1})
        assert result[0].minimum == 1

    def test_maximum(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "integer", "maximum": 100})
        assert result[0].maximum == 100

    def test_pattern(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "string", "pattern": "^[a-z]+$"})
        assert result[0].pattern == "^[a-z]+$"

    def test_enum(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "string", "enum": ["available", "pending", "sold"]})
        assert result[0].enum_values == ["available", "pending", "sold"]

    def test_format(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "string", "format": "email"})
        assert result[0].format == "email"

    def test_format_int64(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "integer", "format": "int64"})
        assert result[0].format == "int64"

    def test_combined_constraints(self):
        parser = SchemaParser()
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 100,
                },
                "status": {
                    "type": "string",
                    "enum": ["available", "pending", "sold"],
                },
            },
        }
        result = parser.infer_types(schema)
        name_field = [f for f in result if f.field_name == "name"][0]
        status_field = [f for f in result if f.field_name == "status"][0]
        assert name_field.min_length == 1
        assert name_field.max_length == 100
        assert name_field.required is True
        assert status_field.enum_values == ["available", "pending", "sold"]
        assert status_field.required is False

    def test_parameter_constraints(self):
        """Parameters can also carry constraints from their schema."""
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        limit_param = [p for p in get_pets[0].parameters if p.name == "limit"][0]
        assert limit_param.constraints[0].minimum == 1
        assert limit_param.constraints[0].maximum == 100


# ---------------------------------------------------------------------------
# 6. Test handling invalid/malformed OpenAPI files
# ---------------------------------------------------------------------------
class TestInvalidInput:
    def test_nonexistent_file_raises(self):
        parser = SchemaParser()
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/path/spec.json")

    def test_invalid_json_raises(self, tmp_path: Path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json!!!")
        parser = SchemaParser()
        with pytest.raises(ValueError):
            parser.parse(str(bad_file))

    def test_invalid_yaml_raises(self, tmp_path: Path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text(":\n  :\n    - {invalid yaml: [")
        parser = SchemaParser()
        with pytest.raises(ValueError):
            parser.parse(str(bad_file))

    def test_missing_openapi_version_raises(self, tmp_path: Path):
        spec = {"info": {"title": "No version", "version": "1.0"}}
        bad_file = tmp_path / "no_version.json"
        bad_file.write_text(json.dumps(spec))
        parser = SchemaParser()
        with pytest.raises(ValueError):
            parser.parse(str(bad_file))

    def test_unsupported_extension_raises(self, tmp_path: Path):
        bad_file = tmp_path / "spec.xml"
        bad_file.write_text("<spec/>")
        parser = SchemaParser()
        with pytest.raises(ValueError):
            parser.parse(str(bad_file))


# ---------------------------------------------------------------------------
# 7. Test handling empty spec returns empty endpoints
# ---------------------------------------------------------------------------
class TestEmptySpec:
    def test_empty_paths_returns_empty_endpoints(self, tmp_path: Path):
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "Empty", "version": "0.1.0"},
            "paths": {},
        }
        f = tmp_path / "empty.json"
        f.write_text(json.dumps(spec))
        parser = SchemaParser()
        result = parser.parse(str(f))
        assert result.endpoints == []

    def test_no_paths_key_returns_empty_endpoints(self, tmp_path: Path):
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "No paths", "version": "0.1.0"},
        }
        f = tmp_path / "no_paths.json"
        f.write_text(json.dumps(spec))
        parser = SchemaParser()
        result = parser.parse(str(f))
        assert result.endpoints == []


# ---------------------------------------------------------------------------
# 8. Test extracting base URL from servers field
# ---------------------------------------------------------------------------
class TestBaseURL:
    def test_base_url_from_json(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        assert result.base_url == "https://petstore.example.com/v1"

    def test_base_url_from_yaml(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_YAML))
        assert result.base_url == "https://petstore-yaml.example.com/v1"

    def test_no_servers_field_returns_none(self, tmp_path: Path):
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "No servers", "version": "0.1.0"},
            "paths": {},
        }
        f = tmp_path / "no_servers.json"
        f.write_text(json.dumps(spec))
        parser = SchemaParser()
        result = parser.parse(str(f))
        assert result.base_url is None

    def test_empty_servers_returns_none(self, tmp_path: Path):
        spec = {
            "openapi": "3.0.3",
            "info": {"title": "Empty servers", "version": "0.1.0"},
            "paths": {},
            "servers": [],
        }
        f = tmp_path / "empty_servers.json"
        f.write_text(json.dumps(spec))
        parser = SchemaParser()
        result = parser.parse(str(f))
        assert result.base_url is None


# ---------------------------------------------------------------------------
# 9. Test parsing request body fields
# ---------------------------------------------------------------------------
class TestRequestBody:
    def test_post_endpoint_has_request_body(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        post_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.POST]
        assert len(post_pets) == 1
        assert post_pets[0].request_body is not None

    def test_request_body_content_type(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        post_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.POST]
        assert post_pets[0].request_body.content_type == "application/json"

    def test_request_body_required(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        post_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.POST]
        assert post_pets[0].request_body.required is True

    def test_request_body_fields_from_ref(self):
        """POST /pets references NewPet via $ref - fields should be resolved."""
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        post_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.POST]
        rb = post_pets[0].request_body
        field_names = {f.field_name for f in rb.fields}
        assert "name" in field_names
        assert "tag" in field_names

    def test_request_body_field_constraints(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        post_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.POST]
        rb = post_pets[0].request_body
        name_field = [f for f in rb.fields if f.field_name == "name"][0]
        assert name_field.required is True
        assert name_field.min_length == 1
        assert name_field.max_length == 100

    def test_yaml_inline_request_body(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_YAML))
        post_users = [e for e in result.endpoints if e.path == "/users" and e.method == HttpMethod.POST]
        rb = post_users[0].request_body
        assert rb is not None
        field_names = {f.field_name for f in rb.fields}
        assert "email" in field_names
        assert "name" in field_names
        assert "age" in field_names

    def test_yaml_request_body_field_constraints(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_YAML))
        post_users = [e for e in result.endpoints if e.path == "/users" and e.method == HttpMethod.POST]
        rb = post_users[0].request_body
        email_field = [f for f in rb.fields if f.field_name == "email"][0]
        assert email_field.format == "email"
        assert email_field.required is True
        age_field = [f for f in rb.fields if f.field_name == "age"][0]
        assert age_field.minimum == 0
        assert age_field.maximum == 150

    def test_get_endpoint_no_request_body(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        assert get_pets[0].request_body is None


# ---------------------------------------------------------------------------
# 10. Test parsing response specifications
# ---------------------------------------------------------------------------
class TestResponseSpecs:
    def test_endpoint_has_responses(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        assert len(get_pets[0].responses) >= 1

    def test_response_status_code(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        status_codes = {r.status_code for r in get_pets[0].responses}
        assert "200" in status_codes

    def test_response_description(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        resp_200 = [r for r in get_pets[0].responses if r.status_code == "200"][0]
        assert resp_200.description == "A list of pets"

    def test_response_content_type(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        resp_200 = [r for r in get_pets[0].responses if r.status_code == "200"][0]
        assert resp_200.content_type == "application/json"

    def test_response_schema_ref(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        resp_200 = [r for r in get_pets[0].responses if r.status_code == "200"][0]
        # The schema references Pet via $ref
        assert resp_200.schema_ref is not None
        assert "Pet" in resp_200.schema_ref

    def test_multiple_responses(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        post_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.POST]
        status_codes = {r.status_code for r in post_pets[0].responses}
        assert "201" in status_codes
        assert "400" in status_codes

    def test_response_without_content(self):
        """Responses like 204 No Content have no content field."""
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        delete_pet = [e for e in result.endpoints if e.path == "/pets/{petId}" and e.method == HttpMethod.DELETE]
        resp_204 = [r for r in delete_pet[0].responses if r.status_code == "204"][0]
        assert resp_204.description == "Pet deleted"
        assert resp_204.content_type is None


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_resolve_ref(self):
        parser = SchemaParser()
        components = {
            "schemas": {
                "Pet": {"type": "object", "properties": {"id": {"type": "integer"}}},
            }
        }
        resolved = parser._resolve_ref("#/components/schemas/Pet", components)
        assert resolved["type"] == "object"
        assert "id" in resolved["properties"]

    def test_resolve_ref_missing_returns_empty(self):
        parser = SchemaParser()
        components = {"schemas": {}}
        resolved = parser._resolve_ref("#/components/schemas/Missing", components)
        assert resolved == {}

    def test_infer_types_empty_schema(self):
        parser = SchemaParser()
        result = parser.infer_types({})
        # No type info -> should return empty or a single unknown field
        assert isinstance(result, list)

    def test_infer_types_no_type_with_properties(self):
        """Object schema without explicit type but with properties."""
        parser = SchemaParser()
        schema = {
            "properties": {
                "foo": {"type": "string"},
            }
        }
        result = parser.infer_types(schema)
        field_names = {f.field_name for f in result}
        assert "foo" in field_names

    def test_default_value(self):
        parser = SchemaParser()
        result = parser.infer_types({"type": "string", "default": "hello"})
        assert result[0].default == "hello"

    def test_parameter_description(self):
        parser = SchemaParser()
        result = parser.parse(str(PETSTORE_JSON))
        get_pets = [e for e in result.endpoints if e.path == "/pets" and e.method == HttpMethod.GET]
        # limit param may or may not have description in fixture; just check structure
        for p in get_pets[0].parameters:
            assert hasattr(p, "description")
