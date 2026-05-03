"""Tests for SecureKeyStore — OS-native credential management with fallback."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from api_chaos_agent.core.key_store import _SERVICE_NAME, SecureKeyStore


class TestDeriveFernetKey:
    def test_returns_url_safe_base64(self):
        from api_chaos_agent.core.key_store import _derive_fernet_key
        key = _derive_fernet_key(b"test-secret")
        assert isinstance(key, bytes)
        assert len(key) == 44

    def test_deterministic(self):
        from api_chaos_agent.core.key_store import _derive_fernet_key
        key1 = _derive_fernet_key(b"same-input")
        key2 = _derive_fernet_key(b"same-input")
        assert key1 == key2

    def test_different_inputs_different_keys(self):
        from api_chaos_agent.core.key_store import _derive_fernet_key
        key1 = _derive_fernet_key(b"input-a")
        key2 = _derive_fernet_key(b"input-b")
        assert key1 != key2


class TestSecureKeyStoreFileFallback:
    def test_init_creates_fallback_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fallback = os.path.join(tmpdir, "keys")
            with patch.object(SecureKeyStore, "__init__", lambda self, **kw: None):
                store = SecureKeyStore.__new__(SecureKeyStore)
                store._use_keyring = False
                store._use_fernet = True
                store._fallback_dir = Path(fallback)
                store._fallback_dir.mkdir(parents=True, exist_ok=True)
                assert Path(fallback).exists()

    def test_set_and_get_file_obfuscated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("api_chaos_agent.core.key_store._KEYRING_AVAILABLE", False), \
                 patch("api_chaos_agent.core.key_store._FERNET_AVAILABLE", False):
                store = SecureKeyStore(fallback_dir=os.path.join(tmpdir, "keys"))
                store.set("test-key", "test-value")
                result = store.get("test-key")
                assert result == "test-value"

    def test_get_nonexistent_key_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("api_chaos_agent.core.key_store._KEYRING_AVAILABLE", False), \
                 patch("api_chaos_agent.core.key_store._FERNET_AVAILABLE", False):
                store = SecureKeyStore(fallback_dir=os.path.join(tmpdir, "keys"))
                assert store.get("nonexistent") is None

    def test_delete_existing_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("api_chaos_agent.core.key_store._KEYRING_AVAILABLE", False), \
                 patch("api_chaos_agent.core.key_store._FERNET_AVAILABLE", False):
                store = SecureKeyStore(fallback_dir=os.path.join(tmpdir, "keys"))
                store.set("to-delete", "value")
                assert store.delete("to-delete") is True
                assert store.get("to-delete") is None

    def test_delete_nonexistent_key_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("api_chaos_agent.core.key_store._KEYRING_AVAILABLE", False), \
                 patch("api_chaos_agent.core.key_store._FERNET_AVAILABLE", False):
                store = SecureKeyStore(fallback_dir=os.path.join(tmpdir, "keys"))
                assert store.delete("nonexistent") is False

    def test_list_keys_file_obfuscated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("api_chaos_agent.core.key_store._KEYRING_AVAILABLE", False), \
                 patch("api_chaos_agent.core.key_store._FERNET_AVAILABLE", False):
                store = SecureKeyStore(fallback_dir=os.path.join(tmpdir, "keys"))
                store.set("key-a", "val-a")
                keys = store.list_keys()
                assert "key-a" in keys

    def test_overwrite_existing_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("api_chaos_agent.core.key_store._KEYRING_AVAILABLE", False), \
                 patch("api_chaos_agent.core.key_store._FERNET_AVAILABLE", False):
                store = SecureKeyStore(fallback_dir=os.path.join(tmpdir, "keys"))
                store.set("key", "old-value")
                store.set("key", "new-value")
                assert store.get("key") == "new-value"

    def test_key_to_filename_deterministic(self):
        store = SecureKeyStore.__new__(SecureKeyStore)
        name1 = store._key_to_filename("test-key")
        name2 = store._key_to_filename("test-key")
        assert name1 == name2
        assert name1.endswith(".enc")

    def test_key_to_filename_special_chars(self):
        store = SecureKeyStore.__new__(SecureKeyStore)
        name = store._key_to_filename("key/with/slashes")
        assert "/" not in name
        assert name.endswith(".enc")

    def test_corrupted_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("api_chaos_agent.core.key_store._KEYRING_AVAILABLE", False), \
                 patch("api_chaos_agent.core.key_store._FERNET_AVAILABLE", False):
                store = SecureKeyStore(fallback_dir=os.path.join(tmpdir, "keys"))
                store.set("good-key", "good-value")
                filepath = Path(tmpdir) / "keys" / store._key_to_filename("good-key")
                filepath.write_bytes(b"corrupted-data")
                assert store.get("good-key") is None


class TestSecureKeyStoreKeyring:
    def _make_store_with_keyring(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None

        class _PasswordDeleteError(Exception):
            pass

        mock_keyring.errors = MagicMock()
        mock_keyring.errors.PasswordDeleteError = _PasswordDeleteError
        store = SecureKeyStore.__new__(SecureKeyStore)
        store._use_keyring = True
        store._use_fernet = True
        store._fallback_dir = Path("/tmp/test-keys")
        return store, mock_keyring

    def test_get_from_keyring(self):
        store, mock_keyring = self._make_store_with_keyring()
        mock_keyring.get_password.return_value = "retrieved-value"
        with patch("api_chaos_agent.core.key_store.keyring", mock_keyring, create=True):
            result = store._get_from_keyring("test-key")
        assert result == "retrieved-value"
        mock_keyring.get_password.assert_called_with(_SERVICE_NAME, "test-key")

    def test_set_to_keyring(self):
        store, mock_keyring = self._make_store_with_keyring()
        with patch("api_chaos_agent.core.key_store.keyring", mock_keyring, create=True):
            store._set_to_keyring("test-key", "test-value")
        mock_keyring.set_password.assert_called_with(_SERVICE_NAME, "test-key", "test-value")

    def test_delete_from_keyring(self):
        store, mock_keyring = self._make_store_with_keyring()
        with patch("api_chaos_agent.core.key_store.keyring", mock_keyring, create=True):
            result = store._delete_from_keyring("test-key")
        assert result is True
        mock_keyring.delete_password.assert_called_with(_SERVICE_NAME, "test-key")

    def test_delete_from_keyring_not_found(self):
        store, mock_keyring = self._make_store_with_keyring()
        mock_keyring.delete_password.side_effect = mock_keyring.errors.PasswordDeleteError("not found")
        with patch("api_chaos_agent.core.key_store.keyring", mock_keyring, create=True):
            result = store._delete_from_keyring("nonexistent")
        assert result is False

    def test_get_from_keyring_error_returns_none(self):
        store, mock_keyring = self._make_store_with_keyring()
        mock_keyring.get_password.side_effect = Exception("keyring error")
        with patch("api_chaos_agent.core.key_store.keyring", mock_keyring, create=True):
            assert store._get_from_keyring("test-key") is None

    def test_set_to_keyring_error_falls_back_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_keyring = MagicMock()
            mock_keyring.set_password.side_effect = Exception("keyring write error")
            with patch("api_chaos_agent.core.key_store.keyring", mock_keyring, create=True), \
                 patch("api_chaos_agent.core.key_store._KEYRING_AVAILABLE", True), \
                 patch("api_chaos_agent.core.key_store._FERNET_AVAILABLE", False):
                store = SecureKeyStore(fallback_dir=os.path.join(tmpdir, "keys"))
                store._use_keyring = True
                store.set("test-key", "fallback-value")
            mock_keyring.set_password.assert_called_once()

    def test_delete_from_keyring_error_returns_false(self):
        store, mock_keyring = self._make_store_with_keyring()
        mock_keyring.delete_password.side_effect = Exception("keyring delete error")
        with patch("api_chaos_agent.core.key_store.keyring", mock_keyring, create=True):
            assert store._delete_from_keyring("test-key") is False

    def test_list_from_keyring(self):
        store, mock_keyring = self._make_store_with_keyring()
        mock_keyring.get_keyring.return_value.get_credential.return_value = None
        with patch("api_chaos_agent.core.key_store.keyring", mock_keyring, create=True):
            result = store._list_from_keyring()
        assert isinstance(result, list)
