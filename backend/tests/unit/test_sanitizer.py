"""Tests for SchemaSanitizer — PII and credential stripping for LLM safety."""

from __future__ import annotations

from api_chaos_agent.core.sanitizer import _REDACTED, SchemaSanitizer


def _make_full_spec() -> dict:
    return {
        "info": {
            "title": "Test API",
            "contact": {"email": "admin@internal.corp", "name": "John Doe"},
        },
        "servers": [
            {"url": "https://api.internal.corp:8443/v1", "variables": {"token": {"default": "secret123"}}}
        ],
        "paths": {
            "/users": {
                "post": {
                    "parameters": [
                        {"name": "api_key", "schema": {"type": "string", "default": "key123", "example": "key123", "enum": ["key123"]}},
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "properties": {
                                        "password": {"type": "string", "default": "pass", "example": "pass"},
                                        "username": {"type": "string"},
                                    }
                                },
                                "example": {"password": "secret", "email": "user@test.com"},
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "headers": {
                                "X-Auth-Token": {"schema": {"default": "tok", "example": "tok"}},
                                "X-Request-Id": {"schema": {"default": "abc"}},
                            }
                        }
                    },
                }
            }
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "description": "Bearer token"},
                "oauth2": {"type": "oauth2", "x-tokenUrl": "https://auth.internal.corp/token"},
            },
            "schemas": {
                "User": {
                    "properties": {
                        "ssn": {"type": "string", "default": "123-45-6789", "example": "123-45-6789"},
                        "name": {"type": "string"},
                    }
                }
            },
        },
        "security": [{"bearerAuth": ["read", "write"]}],
    }


class TestSchemaSanitizerBasic:
    def test_sanitize_returns_spec(self):
        sanitizer = SchemaSanitizer()
        spec = {"info": {}, "paths": {}}
        result = sanitizer.sanitize(spec)
        assert result is spec

    def test_sanitize_empty_spec(self):
        sanitizer = SchemaSanitizer()
        result = sanitizer.sanitize({})
        assert result == {}


class TestSchemaSanitizerServers:
    def test_internal_hostname_sanitized(self):
        sanitizer = SchemaSanitizer()
        spec = {"servers": [{"url": "https://api.internal.corp:8443/v1"}]}
        sanitizer.sanitize(spec)
        assert "[sanitized-host]" in spec["servers"][0]["url"]

    def test_ip_address_sanitized(self):
        sanitizer = SchemaSanitizer()
        spec = {"servers": [{"url": "http://192.168.1.100:8080/api"}]}
        sanitizer.sanitize(spec)
        assert "[sanitized-ip]" in spec["servers"][0]["url"]

    def test_public_url_unchanged(self):
        sanitizer = SchemaSanitizer()
        spec = {"servers": [{"url": "https://api.example.com/v1"}]}
        sanitizer.sanitize(spec)
        assert spec["servers"][0]["url"] == "https://api.example.com/v1"

    def test_server_variables_sensitive_default_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"servers": [{"url": "https://api.example.com", "variables": {"token": {"default": "secret123"}}}]}
        sanitizer.sanitize(spec)
        assert spec["servers"][0]["variables"]["token"]["default"] == _REDACTED

    def test_server_variables_non_sensitive_unchanged(self):
        sanitizer = SchemaSanitizer()
        spec = {"servers": [{"url": "https://api.example.com", "variables": {"version": {"default": "v1"}}}]}
        sanitizer.sanitize(spec)
        assert spec["servers"][0]["variables"]["version"]["default"] == "v1"


class TestSchemaSanitizerParameters:
    def test_sensitive_param_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/users": {"post": {"parameters": [{"name": "password", "schema": {"type": "string", "default": "pass"}}]}}}}
        sanitizer.sanitize(spec)
        param = spec["paths"]["/users"]["post"]["parameters"][0]
        assert param["schema"]["default"] == _REDACTED

    def test_non_sensitive_param_unchanged(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/users": {"get": {"parameters": [{"name": "page", "schema": {"type": "integer", "default": 1}}]}}}}
        sanitizer.sanitize(spec)
        assert spec["paths"]["/users"]["get"]["parameters"][0]["schema"]["default"] == 1

    def test_sensitive_param_enum_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/users": {"post": {"parameters": [{"name": "api_key", "schema": {"type": "string", "enum": ["key1", "key2"]}}]}}}}
        sanitizer.sanitize(spec)
        assert spec["paths"]["/users"]["post"]["parameters"][0]["schema"]["enum"] == [_REDACTED]

    def test_sensitive_param_description_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/users": {"post": {"parameters": [{"name": "password", "description": "User password for login", "schema": {}}]}}}}
        sanitizer.sanitize(spec)
        assert spec["paths"]["/users"]["post"]["parameters"][0]["description"] == _REDACTED


class TestSchemaSanitizerRequestBody:
    def test_sensitive_property_in_schema_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/users": {"post": {"requestBody": {"content": {"application/json": {"schema": {"properties": {"password": {"type": "string", "default": "pass"}}}}}}}}}}
        sanitizer.sanitize(spec)
        schema = spec["paths"]["/users"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        assert schema["properties"]["password"]["default"] == _REDACTED

    def test_sensitive_example_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/users": {"post": {"requestBody": {"content": {"application/json": {"schema": {}, "example": {"password": "secret"}}}}}}}}
        sanitizer.sanitize(spec)
        example = spec["paths"]["/users"]["post"]["requestBody"]["content"]["application/json"]["example"]
        assert example["password"] == _REDACTED

    def test_nested_schema_properties(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/data": {"post": {"requestBody": {"content": {"application/json": {"schema": {"properties": {"config": {"properties": {"secret_key": {"type": "string", "default": "abc"}}}}}}}}}}}}
        sanitizer.sanitize(spec)
        nested = spec["paths"]["/data"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["config"]["properties"]["secret_key"]
        assert nested["default"] == _REDACTED

    def test_items_schema(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/items": {"post": {"requestBody": {"content": {"application/json": {"schema": {"items": {"properties": {"token": {"type": "string", "default": "tok"}}}}}}}}}}}
        sanitizer.sanitize(spec)
        items = spec["paths"]["/items"]["post"]["requestBody"]["content"]["application/json"]["schema"]["items"]
        assert items["properties"]["token"]["default"] == _REDACTED


class TestSchemaSanitizerResponses:
    def test_sensitive_response_header_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/users": {"get": {"responses": {"200": {"headers": {"X-Auth-Token": {"schema": {"default": "tok", "example": "tok"}}}}}}}}}
        sanitizer.sanitize(spec)
        header = spec["paths"]["/users"]["get"]["responses"]["200"]["headers"]["X-Auth-Token"]
        assert header["schema"]["default"] == _REDACTED
        assert header["schema"]["example"] == _REDACTED

    def test_non_sensitive_response_header_unchanged(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/users": {"get": {"responses": {"200": {"headers": {"X-Request-Id": {"schema": {"default": "abc"}}}}}}}}}
        sanitizer.sanitize(spec)
        assert spec["paths"]["/users"]["get"]["responses"]["200"]["headers"]["X-Request-Id"]["schema"]["default"] == "abc"


class TestSchemaSanitizerComponents:
    def test_security_scheme_token_url_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"components": {"securitySchemes": {"oauth": {"type": "oauth2", "x-tokenUrl": "https://auth.corp/token"}}}}
        sanitizer.sanitize(spec)
        assert spec["components"]["securitySchemes"]["oauth"]["x-tokenUrl"] == _REDACTED

    def test_basic_auth_description_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"components": {"securitySchemes": {"basicAuth": {"type": "http", "scheme": "basic", "description": "Basic auth"}}}}
        sanitizer.sanitize(spec)
        assert spec["components"]["securitySchemes"]["basicAuth"]["description"] == _REDACTED

    def test_bearer_auth_description_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"components": {"securitySchemes": {"bearer": {"type": "http", "scheme": "bearer", "description": "Bearer token"}}}}
        sanitizer.sanitize(spec)
        assert spec["components"]["securitySchemes"]["bearer"]["description"] == _REDACTED

    def test_component_schema_sensitive_property(self):
        sanitizer = SchemaSanitizer()
        spec = {"components": {"schemas": {"User": {"properties": {"credit_card_number": {"type": "string", "default": "4111..."}}}}}}
        sanitizer.sanitize(spec)
        assert spec["components"]["schemas"]["User"]["properties"]["credit_card_number"]["default"] == _REDACTED


class TestSchemaSanitizerSecurity:
    def test_security_scopes_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"security": [{"bearerAuth": ["read", "write"]}]}
        sanitizer.sanitize(spec)
        assert spec["security"][0]["bearerAuth"] == [_REDACTED, _REDACTED]

    def test_security_empty_scopes(self):
        sanitizer = SchemaSanitizer()
        spec = {"security": [{"apiKey": []}]}
        sanitizer.sanitize(spec)
        assert spec["security"][0]["apiKey"] == []


class TestSchemaSanitizerInfo:
    def test_contact_email_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"info": {"contact": {"email": "admin@example.com"}}}
        sanitizer.sanitize(spec)
        assert spec["info"]["contact"]["email"] == _REDACTED

    def test_contact_name_redacted(self):
        sanitizer = SchemaSanitizer()
        spec = {"info": {"contact": {"name": "John Doe"}}}
        sanitizer.sanitize(spec)
        assert spec["info"]["contact"]["name"] == _REDACTED

    def test_no_contact_unchanged(self):
        sanitizer = SchemaSanitizer()
        spec = {"info": {"title": "My API"}}
        sanitizer.sanitize(spec)
        assert spec["info"]["title"] == "My API"


class TestSchemaSanitizerFullSpec:
    def test_full_spec_sanitization(self):
        sanitizer = SchemaSanitizer()
        spec = _make_full_spec()
        result = sanitizer.sanitize(spec)
        assert result is spec
        assert spec["info"]["contact"]["email"] == _REDACTED
        assert spec["info"]["contact"]["name"] == _REDACTED
        assert "[sanitized-host]" in spec["servers"][0]["url"]
        assert spec["servers"][0]["variables"]["token"]["default"] == _REDACTED
        assert spec["security"][0]["bearerAuth"] == [_REDACTED, _REDACTED]


class TestSchemaSanitizerHelperMethods:
    def test_is_sensitive_header(self):
        assert SchemaSanitizer._is_sensitive_header("Authorization") is True
        assert SchemaSanitizer._is_sensitive_header("X-Api-Key") is True
        assert SchemaSanitizer._is_sensitive_header("Content-Type") is False

    def test_is_sensitive_param_name(self):
        assert SchemaSanitizer._is_sensitive_param_name("password") is True
        assert SchemaSanitizer._is_sensitive_param_name("api_key") is True
        assert SchemaSanitizer._is_sensitive_param_name("username") is False

    def test_sanitize_url_internal(self):
        sanitizer = SchemaSanitizer()
        assert "[sanitized-host]" in sanitizer._sanitize_url("https://api.internal.corp/v1")

    def test_sanitize_url_ip(self):
        sanitizer = SchemaSanitizer()
        assert "[sanitized-ip]" in sanitizer._sanitize_url("http://10.0.0.1/api")

    def test_sanitize_value_sensitive(self):
        sanitizer = SchemaSanitizer()
        assert sanitizer._sanitize_value("password", "secret") == _REDACTED

    def test_sanitize_value_url(self):
        sanitizer = SchemaSanitizer()
        result = sanitizer._sanitize_value("url", "http://192.168.1.1/api")
        assert "[sanitized-ip]" in result

    def test_sanitize_value_non_string(self):
        sanitizer = SchemaSanitizer()
        assert sanitizer._sanitize_value("count", 42) == 42

    def test_redact_description_sensitive(self):
        sanitizer = SchemaSanitizer()
        assert sanitizer._redact_description("User password for auth") == _REDACTED

    def test_redact_description_non_sensitive(self):
        sanitizer = SchemaSanitizer()
        assert sanitizer._redact_description("Number of items") == "Number of items"

    def test_sanitize_example_nested(self):
        sanitizer = SchemaSanitizer()
        result = sanitizer._sanitize_example({"password": "s", "config": {"token": "t"}})
        assert result["password"] == _REDACTED
        assert result["config"]["token"] == _REDACTED

    def test_non_dict_path_item_skipped(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/test": "not-a-dict"}}
        sanitizer.sanitize(spec)
        assert spec["paths"]["/test"] == "not-a-dict"

    def test_non_dict_operation_skipped(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/test": {"$ref": "string-ref"}}}
        sanitizer.sanitize(spec)
        assert spec["paths"]["/test"]["$ref"] == "string-ref"

    def test_non_dict_response_skipped(self):
        sanitizer = SchemaSanitizer()
        spec = {"paths": {"/test": {"get": {"responses": {"200": "string-ref"}}}}}
        sanitizer.sanitize(spec)
        assert spec["paths"]["/test"]["get"]["responses"]["200"] == "string-ref"
