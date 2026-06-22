import os
from pathlib import Path
from typing import Any

import yaml


class Config:
    _data: dict[str, Any] = {}

    @classmethod
    def load(cls, path: str | Path | None = None) -> dict[str, Any]:
        if path is None:
            path = Path(__file__).parent.parent.parent / "configs" / "default.yaml"

        with open(path) as f:
            raw = yaml.safe_load(f)

        cls._data = cls._resolve_env_vars(raw)
        return cls._data

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value = cls._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    @classmethod
    def all(cls) -> dict[str, Any]:
        return cls._data

    @staticmethod
    def _resolve_env_vars(obj: Any) -> Any:
        if isinstance(obj, str):
            if obj.startswith("${") and obj.endswith("}"):
                expr = obj[2:-1]
                if ":" in expr:
                    env_var, default = expr.split(":", 1)
                    val = os.getenv(env_var)
                    if val is None:
                        return Config._coerce(default)
                    return Config._coerce(val)
                return os.getenv(expr, "")
            return obj
        if isinstance(obj, dict):
            return {k: Config._resolve_env_vars(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [Config._resolve_env_vars(item) for item in obj]
        return obj

    @staticmethod
    def _coerce(val: str) -> Any:
        if val.lower() in ("true", "yes", "1"):
            return True
        if val.lower() in ("false", "no", "0"):
            return False
        try:
            return int(val)
        except ValueError:
            pass
        try:
            return float(val)
        except ValueError:
            pass
        return val
