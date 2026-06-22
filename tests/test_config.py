"""Unit tests for Config class."""

import os

from backend.utils.config import Config


class TestConfig:
    def setup_method(self):
        Config._data = {}

    def test_load_defaults(self):
        Config.load()
        assert Config.get("auth.enabled") is True
        assert Config.get("server.port") == 8000
        assert Config.get("logging.level") == "INFO"

    def test_get_nested(self):
        Config._data = {"a": {"b": {"c": 42}}}
        assert Config.get("a.b.c") == 42
        assert Config.get("a.b") == {"c": 42}

    def test_get_default(self):
        assert Config.get("nonexistent.key", "default") == "default"
        assert Config.get("nonexistent") is None

    def test_env_var_resolution(self):
        os.environ["_TEST_VAR"] = "test_value"
        result = Config._resolve_env_vars("${_TEST_VAR}")
        assert result == "test_value"
        del os.environ["_TEST_VAR"]

    def test_env_var_with_default(self):
        result = Config._resolve_env_vars("${_NONEXISTENT_VAR:fallback}")
        assert result == "fallback"

    def test_env_var_bool_coercion(self):
        result = Config._resolve_env_vars("${_BOOL_VAR:true}")
        assert result is True

        result = Config._resolve_env_vars("${_BOOL_VAR:false}")
        assert result is False

    def test_env_var_int_coercion(self):
        result = Config._resolve_env_vars("${_INT_VAR:42}")
        assert result == 42

    def test_all_returns_loaded_data(self):
        Config._data = {"key": "value"}
        assert Config.all() == {"key": "value"}
