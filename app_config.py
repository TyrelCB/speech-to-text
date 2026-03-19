"""
Configuration helpers for the Speech-to-Text Engine.
"""

import copy
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

VALID_MODEL_SIZES = {"tiny", "base", "small", "medium", "large"}
VALID_DEVICE_PREFERENCES = {"auto", "cpu", "gpu"}

DEFAULT_CONFIG = {
    "hotkey": "Ctrl+Space",
    "hotkey_mode": "toggle",
    "model_size": "small",
    "device_preference": "auto",
    "language": "en",
    "audio_chunk_duration": 5,
    "max_record_seconds": 600,
    "audio_sample_rate": 16000,
    "audio_channels": 1,
    "overlay_timeout": 3,
    "overlay_font_size": 16,
    "audio_buffer_size": 1024,
}


def _load_json_file(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Configuration file must contain a JSON object: {path}")
    return data


def load_config(config_dir: str | None = None) -> dict[str, Any]:
    """Load base config and merge any untracked local overrides."""
    if config_dir is None:
        config_dir = os.path.dirname(os.path.abspath(__file__))

    config = copy.deepcopy(DEFAULT_CONFIG)
    base_config_path = os.path.join(config_dir, "config.json")
    local_config_path = os.path.join(config_dir, "config.local.json")

    try:
        config.update(_load_json_file(base_config_path))
    except FileNotFoundError:
        logger.error("Configuration file not found: %s", base_config_path)

    try:
        local_config = _load_json_file(local_config_path)
    except FileNotFoundError:
        return config

    logger.info("Loaded local config overrides from %s", local_config_path)
    config.update(local_config)
    return config


def validate_config(config: dict[str, Any]):
    """Validate config values; raise ValueError with a clear message on bad input."""
    model_size = config.get("model_size", DEFAULT_CONFIG["model_size"])
    if model_size not in VALID_MODEL_SIZES:
        raise ValueError(
            f"Invalid model_size '{model_size}'. Must be one of: {', '.join(sorted(VALID_MODEL_SIZES))}"
        )

    device_preference = str(
        config.get("device_preference", DEFAULT_CONFIG["device_preference"])
    ).lower()
    if device_preference not in VALID_DEVICE_PREFERENCES:
        raise ValueError(
            "Config key 'device_preference' must be 'auto', 'cpu', or 'gpu', "
            f"got: {device_preference!r}"
        )

    for int_key in (
        "audio_chunk_duration",
        "audio_sample_rate",
        "audio_channels",
        "overlay_timeout",
        "overlay_font_size",
        "audio_buffer_size",
        "max_record_seconds",
    ):
        val = config.get(int_key)
        if val is not None and (not isinstance(val, int) or val <= 0):
            raise ValueError(f"Config key '{int_key}' must be a positive integer, got: {val!r}")

    hotkey = config.get("hotkey", "")
    if not isinstance(hotkey, str) or not hotkey:
        raise ValueError(f"Config key 'hotkey' must be a non-empty string, got: {hotkey!r}")

    hotkey_mode = str(config.get("hotkey_mode", DEFAULT_CONFIG["hotkey_mode"])).lower()
    if hotkey_mode not in {"hold", "toggle"}:
        raise ValueError(
            f"Config key 'hotkey_mode' must be 'hold' or 'toggle', got: {hotkey_mode!r}"
        )
