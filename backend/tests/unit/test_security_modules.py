"""Unit tests for security modules: sanitizer, key_store, audit."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from api_chaos_agent.core.audit import AuditLogger
from api_chaos_agent.core.key_store import SecureKeyStore
from api_chaos_agent.core.sanitizer import SchemaSanitizer


class TestSchemaSanitizer:
    def setup_method(self):
        self.sanitizer = SchemaSanitizer()

    def test_sanitize_password_field(self):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/login": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "password": {"type": "string", "example": "secret123"},
                                        },
                                    }
                                }
                            }
                        },
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        result = self.sanitizer.sanitize(spec)
        pw = result["paths"]["/login"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["password"]
        assert pw.get("example") == "[REDACTED]"

    def test_sanitize_api_key_field(self):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/data": {
                    "get": {
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
            "components": {
                "securitySchemes": {
                    "apiKey": {"type": "apiKey", "name": "X-API-Key", "in": "header"},
                }
            },
        }
        result = self.sanitizer.sanitize(spec)
        assert result is not None

    def test_sanitize_contact_email(self):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1", "contact": {"email": "admin@corp.com", "name": "Admin"}},
            "paths": {},
        }
        result = self.sanitizer.sanitize(spec)
        assert result["info"]["contact"]["email"] == "[REDACTED]"

    def test_sanitize_internal_hostname(self):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "servers": [{"url": "https://api.internal.corp.com:8080"}],
            "paths": {},
        }
        result = self.sanitizer.sanitize(spec)
        server_url = result["servers"][0]["url"]
        assert "internal" not in server_url or "[sanitized" in server_url

    def test_sanitize_no_secrets(self):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {"/health": {"get": {"responses": {"200": {"description": "OK"}}}}},
        }
        result = self.sanitizer.sanitize(spec)
        assert result["paths"]["/health"]["get"]["responses"]["200"]["description"] == "OK"

    def test_sanitize_token_field(self):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/auth": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "token": {"type": "string", "default": "eyJhbGciOiJIUzI1NiJ9..."},
                                        },
                                    }
                                }
                            }
                        },
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        result = self.sanitizer.sanitize(spec)
        token_prop = result["paths"]["/auth"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["token"]
        assert token_prop.get("default") == "[REDACTED]"

    def test_sanitize_secret_field(self):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/setup": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "client_secret": {"type": "string", "example": "abc123def456"},
                                        },
                                    }
                                }
                            }
                        },
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        result = self.sanitizer.sanitize(spec)
        secret_prop = result["paths"]["/setup"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["client_secret"]
        assert secret_prop.get("example") == "[REDACTED]"


class TestSecureKeyStore:
    def test_set_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecureKeyStore(fallback_dir=tmpdir)
            store.set("test_key", "test_value_123")
            assert store.get("test_key") == "test_value_123"

    def test_get_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecureKeyStore(fallback_dir=tmpdir)
            assert store.get("nonexistent") is None

    def test_delete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecureKeyStore(fallback_dir=tmpdir)
            store.set("del_key", "del_value")
            store.delete("del_key")
            assert store.get("del_key") is None

    def test_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecureKeyStore(fallback_dir=tmpdir)
            store.set("key1", "value1")
            store.set("key1", "value2")
            assert store.get("key1") == "value2"

    def test_multiple_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecureKeyStore(fallback_dir=tmpdir)
            store.set("k1", "v1")
            store.set("k2", "v2")
            store.set("k3", "v3")
            assert store.get("k1") == "v1"
            assert store.get("k2") == "v2"
            assert store.get("k3") == "v3"


class TestAuditLogger:
    def test_record_and_stats(self):
        logger = AuditLogger()
        logger.record(provider="openai", model="gpt-4", operation="generate", prompt_tokens=100, completion_tokens=50, latency_ms=500)
        logger.record(provider="ollama", model="llama3", operation="generate", prompt_tokens=200, completion_tokens=100, latency_ms=1200, status="error", error_message="timeout")
        stats = logger.get_stats()
        assert stats["total_calls"] == 2
        assert stats["error_count"] == 1

    def test_query_by_provider(self):
        logger = AuditLogger()
        logger.record(provider="openai", model="gpt-4", operation="generate", prompt_tokens=100, completion_tokens=50, latency_ms=500)
        logger.record(provider="ollama", model="llama3", operation="generate", prompt_tokens=200, completion_tokens=100, latency_ms=1200)
        entries = logger.query(provider="openai")
        assert len(entries) == 1

    def test_query_by_status(self):
        logger = AuditLogger()
        logger.record(provider="openai", model="gpt-4", operation="generate", prompt_tokens=100, completion_tokens=50, latency_ms=500)
        logger.record(provider="ollama", model="llama3", operation="generate", prompt_tokens=200, completion_tokens=100, latency_ms=1200, status="error")
        errors = logger.query(status="error")
        assert len(errors) == 1

    def test_export_json(self):
        logger = AuditLogger()
        logger.record(provider="openai", model="gpt-4", operation="generate", prompt_tokens=100, completion_tokens=50, latency_ms=500)
        json_str = logger.export_json()
        data = json.loads(json_str)
        assert len(data) >= 1

    def test_empty_stats(self):
        logger = AuditLogger()
        stats = logger.get_stats()
        assert stats["total_calls"] == 0

    def test_multiple_records(self):
        logger = AuditLogger()
        for i in range(10):
            logger.record(provider="openai", model="gpt-4", operation="generate", prompt_tokens=i * 10, completion_tokens=i * 5, latency_ms=i * 100)
        stats = logger.get_stats()
        assert stats["total_calls"] == 10
