from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


DEFAULT_APP_CONFIG: dict[str, Any] = {
    "language": {
        "preferredResponseLanguage": "Hinglish",
        "transcriptionLanguage": "Auto",
        "keepTechnicalTermsEnglish": True,
    },
    "activeAgentId": "code_assistant",
    "inputMode": "agent",
}


def read_json_config(name: str, default: dict[str, Any]) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        return default.copy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default.copy()
    if not isinstance(data, dict):
        return default.copy()
    return deep_merge(default, data)


def write_json_config(name: str, data: dict[str, Any]) -> dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def get_app_config() -> dict[str, Any]:
    return read_json_config("app_config.json", DEFAULT_APP_CONFIG)


def save_app_config(update: dict[str, Any]) -> dict[str, Any]:
    current = get_app_config()
    saved = deep_merge(current, update)
    return write_json_config("app_config.json", saved)


def get_platform_config() -> dict[str, Any]:
    return {
        "app": get_app_config(),
        "agents": read_json_config("agents.json", {"agents": []}),
        "providers": read_json_config("providers.json", {}),
        "permissions": read_json_config("permissions.json", {}),
    }


def deep_merge(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
