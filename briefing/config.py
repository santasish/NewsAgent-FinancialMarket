from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

_MISSING = object()


@dataclass
class Config:
    data: dict
    root: Path

    def get(self, path: str, default: Any = _MISSING) -> Any:
        node: Any = self.data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                if default is _MISSING:
                    raise KeyError(f"missing config key: {path}")
                return default
            node = node[part]
        return node

    def secret(self, name: str, default: Any = _MISSING) -> str:
        value = os.environ.get(name)
        if value:
            return value
        if default is _MISSING:
            raise KeyError(f"missing environment variable: {name}")
        return default

    def path(self, key: str) -> Path:
        return self.root / self.get(key)

    @property
    def prompts_dir(self) -> Path:
        return self.root / "prompts"


def load_config(config_path: Path | None = None) -> Config:
    load_dotenv(ROOT / ".env")
    path = config_path or ROOT / "config.yaml"
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return Config(data=data, root=ROOT)
