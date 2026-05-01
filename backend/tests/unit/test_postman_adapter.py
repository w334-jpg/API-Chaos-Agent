"""Unit tests for Postman adapter."""

from __future__ import annotations

import json

from api_chaos_agent.models.schema import HttpMethod
from api_chaos_agent.services.postman_adapter import PostmanAdapter


class TestPostmanImport:
    def setup_method(self):
        self.adapter = PostmanAdapter()

    def test_import_v21_collection(self):
        collection = {
            "info": {
                "name": "Test",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [
                {
                    "name": "Get Users",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "https://api.example.com/users",
                            "protocol": "https",
                            "host": ["api", "example", "com"],
                            "path": ["users"],
                        },
                    },
                    "response": [],
                }
            ],
        }
        spec = self.adapter.import_collection(collection)
        assert spec is not None
        assert len(spec.endpoints) == 1
        assert spec.endpoints[0].method == HttpMethod.GET
        assert spec.endpoints[0].path == "/users"

    def test_import_post_with_body(self):
        collection = {
            "info": {
                "name": "T",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [
                {
                    "name": "Create User",
                    "request": {
                        "method": "POST",
                        "header": [{"key": "Content-Type", "value": "application/json"}],
                        "body": {"mode": "raw", "raw": json.dumps({"name": "John"})},
                        "url": {
                            "raw": "https://api.example.com/users",
                            "protocol": "https",
                            "host": ["api", "example", "com"],
                            "path": ["users"],
                        },
                    },
                    "response": [],
                }
            ],
        }
        spec = self.adapter.import_collection(collection)
        assert spec is not None
        post_endpoints = [e for e in spec.endpoints if e.method == HttpMethod.POST]
        assert len(post_endpoints) == 1

    def test_import_with_query_params(self):
        collection = {
            "info": {
                "name": "T",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [
                {
                    "name": "Search",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "https://api.example.com/search?q=test&page=1",
                            "protocol": "https",
                            "host": ["api", "example", "com"],
                            "path": ["search"],
                            "query": [{"key": "q", "value": "test"}, {"key": "page", "value": "1"}],
                        },
                    },
                    "response": [],
                }
            ],
        }
        spec = self.adapter.import_collection(collection)
        assert spec is not None
        assert len(spec.endpoints[0].parameters) >= 1

    def test_import_empty_collection(self):
        collection = {
            "info": {
                "name": "Empty",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [],
        }
        spec = self.adapter.import_collection(collection)
        assert spec is not None
        assert len(spec.endpoints) == 0

    def test_import_multiple_methods(self):
        collection = {
            "info": {
                "name": "T",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [
                {
                    "name": "List",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "https://api.example.com/items",
                            "host": ["api", "example", "com"],
                            "path": ["items"],
                        },
                    },
                    "response": [],
                },
                {
                    "name": "Create",
                    "request": {
                        "method": "POST",
                        "header": [],
                        "url": {
                            "raw": "https://api.example.com/items",
                            "host": ["api", "example", "com"],
                            "path": ["items"],
                        },
                    },
                    "response": [],
                },
                {
                    "name": "Update",
                    "request": {
                        "method": "PUT",
                        "header": [],
                        "url": {
                            "raw": "https://api.example.com/items/1",
                            "host": ["api", "example", "com"],
                            "path": ["items", "1"],
                        },
                    },
                    "response": [],
                },
                {
                    "name": "Delete",
                    "request": {
                        "method": "DELETE",
                        "header": [],
                        "url": {
                            "raw": "https://api.example.com/items/1",
                            "host": ["api", "example", "com"],
                            "path": ["items", "1"],
                        },
                    },
                    "response": [],
                },
            ],
        }
        spec = self.adapter.import_collection(collection)
        methods = {e.method for e in spec.endpoints}
        assert HttpMethod.GET in methods
        assert HttpMethod.POST in methods
        assert HttpMethod.PUT in methods
        assert HttpMethod.DELETE in methods


class TestPostmanExport:
    def setup_method(self):
        self.adapter = PostmanAdapter()

    def test_export_has_v21_schema(self):
        from api_chaos_agent.models.schema import APISpec, Endpoint

        spec = APISpec(
            title="Test", version="1.0", endpoints=[Endpoint(path="/test", method=HttpMethod.GET)]
        )
        export = self.adapter.export_collection(spec)
        assert "v2.1" in export.get("info", {}).get("schema", "")

    def test_export_preserves_endpoints(self):
        from api_chaos_agent.models.schema import APISpec, Endpoint

        spec = APISpec(
            title="Test",
            version="1.0",
            endpoints=[
                Endpoint(path="/users", method=HttpMethod.GET),
                Endpoint(path="/users", method=HttpMethod.POST),
            ],
        )
        export = self.adapter.export_collection(spec)
        assert len(export.get("item", [])) == 2

    def test_roundtrip(self):
        collection = {
            "info": {
                "name": "T",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": [
                {
                    "name": "Get Items",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "https://api.example.com/items",
                            "host": ["api", "example", "com"],
                            "path": ["items"],
                        },
                    },
                    "response": [],
                },
            ],
        }
        spec = self.adapter.import_collection(collection)
        export = self.adapter.export_collection(spec)
        reimported = self.adapter.import_collection(export)
        assert len(reimported.endpoints) == 1
        assert reimported.endpoints[0].method == HttpMethod.GET
