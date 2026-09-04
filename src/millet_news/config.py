from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    with target.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_all() -> dict[str, Any]:
    settings = load_yaml("config/settings.yaml")
    settings["branding"] = load_yaml("config/branding.yaml")
    settings["keywords"] = load_yaml("config/keywords.yaml")
    settings["source_config"] = load_yaml("config/sources.yaml")
    settings["root"] = ROOT
    return settings


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}
