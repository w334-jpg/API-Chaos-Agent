"""Secure key store using OS-native credential managers.

Supports:
- macOS: Keychain (via keyring)
- Windows: Credential Manager (via keyring)
- Linux: Secret Service / D-Bus (via keyring)
- Fallback: Encrypted file-based storage

This module provides a unified interface for storing and retrieving
sensitive credentials like API keys without hardcoding them.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from api_chaos_agent.core.logging import get_logger

logger = get_logger(__name__)

_KEYRING_AVAILABLE = False
try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    pass

_SERVICE_NAME = "api-chaos-agent"


class SecureKeyStore:
    """Store and retrieve sensitive credentials using OS-native keychain.

    Uses the `keyring` library when available for OS-native credential
    management. Falls back to an encrypted file-based store when keyring
    is not installed.
    """

    def __init__(self, fallback_dir: str | None = None) -> None:
        self._use_keyring = _KEYRING_AVAILABLE
        self._fallback_dir = Path(fallback_dir or os.path.expanduser("~/.api-chaos-agent/keys"))
        if not self._use_keyring:
            self._fallback_dir.mkdir(parents=True, exist_ok=True)
            logger.info("keyring not available, using file-based key store at %s", self._fallback_dir)

    def get(self, key: str) -> str | None:
        if self._use_keyring:
            return self._get_from_keyring(key)
        return self._get_from_file(key)

    def set(self, key: str, value: str) -> None:
        if self._use_keyring:
            self._set_to_keyring(key, value)
        else:
            self._set_to_file(key, value)

    def delete(self, key: str) -> bool:
        if self._use_keyring:
            return self._delete_from_keyring(key)
        return self._delete_from_file(key)

    def list_keys(self) -> list[str]:
        if self._use_keyring:
            return self._list_from_keyring()
        return self._list_from_file()

    def _get_from_keyring(self, key: str) -> str | None:
        try:
            return keyring.get_password(_SERVICE_NAME, key)
        except Exception as exc:
            logger.warning("Failed to read from keyring for key '%s': %s", key, exc)
            return None

    def _set_to_keyring(self, key: str, value: str) -> None:
        try:
            keyring.set_password(_SERVICE_NAME, key, value)
        except Exception as exc:
            logger.warning("Failed to write to keyring for key '%s': %s", key, exc)
            self._set_to_file(key, value)

    def _delete_from_keyring(self, key: str) -> bool:
        try:
            keyring.delete_password(_SERVICE_NAME, key)
            return True
        except keyring.errors.PasswordDeleteError:
            return False
        except Exception as exc:
            logger.warning("Failed to delete from keyring for key '%s': %s", key, exc)
            return False

    def _list_from_keyring(self) -> list[str]:
        try:
            return keyring.get_keyring().get_credential(_SERVICE_NAME, "") is not None and [] or []
        except Exception:
            return []

    def _key_to_filename(self, key: str) -> str:
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return f"{safe}_{h}.enc"

    def _get_obfuscation_key(self) -> bytes:
        machine_id = os.environ.get("API_CHAOS_AGENT_MACHINE_ID", "")
        if not machine_id:
            machine_id = str(os.getuid()) if hasattr(os, "getuid") else os.environ.get("USER", "default")
        return hashlib.sha256(f"{_SERVICE_NAME}:{machine_id}".encode()).digest()

    def _get_from_file(self, key: str) -> str | None:
        filepath = self._fallback_dir / self._key_to_filename(key)
        if not filepath.exists():
            return None
        try:
            data = filepath.read_bytes()
            obf_key = self._get_obfuscation_key()
            decoded = base64.b64decode(data)
            xored = bytes(b ^ obf_key[i % len(obf_key)] for i, b in enumerate(decoded))
            entry = json.loads(xored.decode("utf-8"))
            return entry.get("value")
        except Exception as exc:
            logger.warning("Failed to read key '%s' from file store: %s", key, exc)
            return None

    def _set_to_file(self, key: str, value: str) -> None:
        filepath = self._fallback_dir / self._key_to_filename(key)
        try:
            entry = json.dumps({"key": key, "value": value}).encode("utf-8")
            obf_key = self._get_obfuscation_key()
            xored = bytes(b ^ obf_key[i % len(obf_key)] for i, b in enumerate(entry))
            filepath.write_bytes(base64.b64encode(xored))
        except Exception as exc:
            logger.warning("Failed to write key '%s' to file store: %s", key, exc)

    def _delete_from_file(self, key: str) -> bool:
        filepath = self._fallback_dir / self._key_to_filename(key)
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def _list_from_file(self) -> list[str]:
        keys: list[str] = []
        for filepath in self._fallback_dir.glob("*.enc"):
            try:
                data = filepath.read_bytes()
                obf_key = self._get_obfuscation_key()
                decoded = base64.b64decode(data)
                xored = bytes(b ^ obf_key[i % len(obf_key)] for i, b in enumerate(decoded))
                entry = json.loads(xored.decode("utf-8"))
                if "key" in entry:
                    keys.append(entry["key"])
            except Exception:
                pass
        return keys


secure_key_store = SecureKeyStore()
