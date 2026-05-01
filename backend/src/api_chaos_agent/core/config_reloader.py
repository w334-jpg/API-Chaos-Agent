"""Configuration hot-reload mechanism.

Watches the config file for changes and notifies registered callbacks.
Uses atomic replacement instead of mutating frozen dataclasses to
maintain thread safety and immutability guarantees.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from api_chaos_agent.core.config import AppConfig, settings
from api_chaos_agent.core.logging import get_logger

logger = get_logger(__name__)

Callback = Callable[[AppConfig], None]


class ConfigReloader:
    """File-watcher that hot-reloads configuration changes.

    Instead of mutating the frozen `settings` dataclass (which would
    violate immutability), this creates a new AppConfig instance and
    atomically swaps the module-level `settings` reference.

    Usage:
        reloader = ConfigReloader()
        reloader.on_change("auth", my_callback)
        reloader.start()
    """

    def __init__(self, config_path: str | None = None) -> None:
        self._config_path = Path(config_path or "config/default.toml")
        self._callbacks: dict[str, list[Callback]] = {}
        self._hash: str = self._compute_hash()
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._interval = 5.0

    def _compute_hash(self) -> str:
        if not self._config_path.exists():
            return ""
        return hashlib.md5(self._config_path.read_bytes()).hexdigest()

    def on_change(self, section: str, callback: Callback) -> None:
        self._callbacks.setdefault(section, []).append(callback)

    def _notify(self, new_config: AppConfig) -> None:
        import api_chaos_agent.core.config as config_mod
        with self._lock:
            old_config = config_mod.settings
            config_mod.settings = new_config

        for section, callbacks in self._callbacks.items():
            old_val = getattr(old_config, section, None)
            new_val = getattr(new_config, section, None)
            if old_val != new_val:
                for cb in callbacks:
                    try:
                        cb(new_config)
                    except Exception:
                        logger.exception("config_reload_callback_error", section=section)

    def check_and_reload(self) -> bool:
        current_hash = self._compute_hash()
        if current_hash == self._hash:
            return False
        self._hash = current_hash
        logger.info("config_file_changed", path=str(self._config_path))

        try:
            new_config = self._load_config()
        except Exception:
            logger.exception("config_reload_error")
            return False

        self._notify(new_config)
        return True

    def _load_config(self) -> AppConfig:
        import api_chaos_agent.core.config as config_mod
        old = config_mod.settings
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        if not self._config_path.exists():
            return old

        with open(self._config_path, "rb") as f:
            data = tomllib.load(f)

        new_store = replace(old.store, **data.get("store", {}))
        new_execution = replace(old.execution, **data.get("execution", {}))
        new_llm = replace(old.llm, **data.get("llm", {}))
        new_server = replace(old.server, **data.get("server", {}))
        new_auth = replace(old.auth, **data.get("auth", {}))
        new_rate_limit = replace(old.rate_limit, **data.get("rate_limit", {}))
        new_logging = replace(old.logging, **data.get("logging", {}))

        return AppConfig(
            store=new_store,
            execution=new_execution,
            llm=new_llm,
            server=new_server,
            auth=new_auth,
            rate_limit=new_rate_limit,
            logging=new_logging,
        )

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None

    def _watch_loop(self) -> None:
        import time
        while self._running:
            try:
                self.check_and_reload()
            except Exception:
                logger.exception("config_watch_error")
            time.sleep(self._interval)
