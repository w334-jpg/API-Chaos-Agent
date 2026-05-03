"""Tests for ConfigReloader — configuration hot-reload mechanism."""

from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

import api_chaos_agent.core.config as config_mod
from api_chaos_agent.core.config import AppConfig
from api_chaos_agent.core.config_reloader import ConfigReloader


class TestConfigReloaderInit:
    def test_init_default_config_path(self):
        reloader = ConfigReloader()
        assert reloader._config_path == Path("config/default.toml")

    def test_init_custom_config_path(self):
        reloader = ConfigReloader(config_path="/tmp/custom.toml")
        assert reloader._config_path == Path("/tmp/custom.toml")

    def test_init_not_running(self):
        reloader = ConfigReloader()
        assert reloader._running is False

    def test_init_no_thread(self):
        reloader = ConfigReloader()
        assert reloader._thread is None


class TestConfigReloaderHash:
    def test_compute_hash_nonexistent_file(self):
        reloader = ConfigReloader(config_path="/tmp/nonexistent_config.toml")
        assert reloader._compute_hash() == ""

    def test_compute_hash_existing_file(self):
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(b"[store]\nmax_schemas = 500\n")
            f.flush()
            reloader = ConfigReloader(config_path=f.name)
            h = reloader._compute_hash()
            assert len(h) == 64
            assert h != ""

    def test_hash_changes_on_file_update(self):
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="wb") as f:
            f.write(b"[store]\nmax_schemas = 500\n")
            f.flush()
            reloader = ConfigReloader(config_path=f.name)
            h1 = reloader._compute_hash()
            f.write(b"[store]\nmax_schemas = 1000\n")
            f.flush()
            h2 = reloader._compute_hash()
            assert h1 != h2


class TestConfigReloaderCallbacks:
    def test_register_callback(self):
        reloader = ConfigReloader()
        called = []
        reloader.on_change("store", lambda cfg: called.append(cfg))
        assert "store" in reloader._callbacks
        assert len(reloader._callbacks["store"]) == 1

    def test_multiple_callbacks_same_section(self):
        reloader = ConfigReloader()
        reloader.on_change("store", lambda cfg: None)
        reloader.on_change("store", lambda cfg: None)
        assert len(reloader._callbacks["store"]) == 2

    def test_callbacks_different_sections(self):
        reloader = ConfigReloader()
        reloader.on_change("store", lambda cfg: None)
        reloader.on_change("auth", lambda cfg: None)
        assert "store" in reloader._callbacks
        assert "auth" in reloader._callbacks


class TestConfigReloaderCheckAndReload:
    def test_check_no_change_returns_false(self):
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(b"[store]\nmax_schemas = 500\n")
            f.flush()
            reloader = ConfigReloader(config_path=f.name)
            assert reloader.check_and_reload() is False

    def test_check_nonexistent_path_returns_false(self):
        reloader = ConfigReloader(config_path="/tmp/nonexistent_config.toml")
        assert reloader.check_and_reload() is False

    def test_check_with_invalid_toml_returns_false(self):
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as f:
            f.write("this is not valid toml {{{")
            f.flush()
            reloader = ConfigReloader(config_path=f.name)
            reloader._hash = "different_hash"
            result = reloader.check_and_reload()
            assert result is False


class TestConfigReloaderStartStop:
    def test_start_sets_running(self):
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(b"[store]\nmax_schemas = 500\n")
            f.flush()
            reloader = ConfigReloader(config_path=f.name)
            reloader._interval = 0.1
            reloader.start()
            assert reloader._running is True
            reloader.stop()
            assert reloader._running is False

    def test_stop_without_start(self):
        reloader = ConfigReloader()
        reloader.stop()
        assert reloader._running is False

    def test_start_idempotent(self):
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(b"[store]\nmax_schemas = 500\n")
            f.flush()
            reloader = ConfigReloader(config_path=f.name)
            reloader._interval = 0.1
            reloader.start()
            thread1 = reloader._thread
            reloader.start()
            thread2 = reloader._thread
            assert thread1 is thread2
            reloader.stop()

    def test_start_stop_lifecycle(self):
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(b"[store]\nmax_schemas = 500\n")
            f.flush()
            reloader = ConfigReloader(config_path=f.name)
            reloader._interval = 0.1
            reloader.start()
            assert reloader._running is True
            reloader.stop()
            assert reloader._running is False
            assert reloader._thread is None


class TestConfigReloaderNotify:
    def test_notify_calls_registered_callback(self):
        reloader = ConfigReloader()
        results = []
        reloader.on_change("auth", lambda cfg: results.append("called"))
        current = config_mod.settings
        new_auth = replace(current.auth, enabled=not current.auth.enabled)
        new_config = replace(current, auth=new_auth)
        reloader._notify(new_config)
        assert len(results) == 1

    def test_notify_skips_when_section_unchanged(self):
        reloader = ConfigReloader()
        results = []
        reloader.on_change("store", lambda cfg: results.append("called"))
        current = config_mod.settings
        reloader._notify(current)
        assert len(results) == 0

    def test_notify_handles_callback_exception(self):
        reloader = ConfigReloader()
        reloader.on_change("auth", lambda cfg: 1 / 0)
        new_config = AppConfig()
        reloader._notify(new_config)
