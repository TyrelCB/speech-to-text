"""Tests for config schema validation."""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_config import load_config
from main import validate_config


def _base_config():
    return {
        'hotkey': 'Ctrl+Shift+M',
        'hotkey_mode': 'hold',
        'model_size': 'small',
        'device_preference': 'auto',
        'audio_chunk_duration': 5,
        'max_record_seconds': 600,
        'audio_sample_rate': 16000,
        'audio_channels': 1,
        'overlay_timeout': 3,
        'overlay_font_size': 16,
        'audio_buffer_size': 1024,
    }


def test_valid_config_passes():
    validate_config(_base_config())


def test_invalid_model_size_raises():
    cfg = _base_config()
    cfg['model_size'] = 'giant'
    with pytest.raises(ValueError, match="model_size"):
        validate_config(cfg)


@pytest.mark.parametrize("model_size", ['tiny', 'base', 'small', 'medium', 'large'])
def test_all_valid_model_sizes_pass(model_size):
    cfg = _base_config()
    cfg['model_size'] = model_size
    validate_config(cfg)


@pytest.mark.parametrize("device_preference", ['auto', 'cpu', 'gpu'])
def test_all_valid_device_preferences_pass(device_preference):
    cfg = _base_config()
    cfg['device_preference'] = device_preference
    validate_config(cfg)


def test_invalid_device_preference_raises():
    cfg = _base_config()
    cfg['device_preference'] = 'tpu'
    with pytest.raises(ValueError, match="device_preference"):
        validate_config(cfg)


def test_negative_audio_sample_rate_raises():
    cfg = _base_config()
    cfg['audio_sample_rate'] = -1
    with pytest.raises(ValueError, match="audio_sample_rate"):
        validate_config(cfg)


def test_zero_chunk_duration_raises():
    cfg = _base_config()
    cfg['audio_chunk_duration'] = 0
    with pytest.raises(ValueError, match="audio_chunk_duration"):
        validate_config(cfg)


def test_zero_max_record_seconds_raises():
    cfg = _base_config()
    cfg['max_record_seconds'] = 0
    with pytest.raises(ValueError, match="max_record_seconds"):
        validate_config(cfg)


def test_empty_hotkey_raises():
    cfg = _base_config()
    cfg['hotkey'] = ''
    with pytest.raises(ValueError, match="hotkey"):
        validate_config(cfg)


def test_non_string_hotkey_raises():
    cfg = _base_config()
    cfg['hotkey'] = 42
    with pytest.raises(ValueError, match="hotkey"):
        validate_config(cfg)


def test_invalid_hotkey_mode_raises():
    cfg = _base_config()
    cfg['hotkey_mode'] = 'tap'
    with pytest.raises(ValueError, match="hotkey_mode"):
        validate_config(cfg)


def test_load_config_merges_local_overrides(tmp_path):
    base_config = _base_config()
    local_override = {'model_size': 'tiny', 'device_preference': 'cpu'}

    (tmp_path / 'config.json').write_text(
        __import__('json').dumps(base_config),
        encoding='utf-8',
    )
    (tmp_path / 'config.local.json').write_text(
        __import__('json').dumps(local_override),
        encoding='utf-8',
    )

    config = load_config(str(tmp_path))

    assert config['hotkey'] == base_config['hotkey']
    assert config['model_size'] == 'tiny'
    assert config['device_preference'] == 'cpu'
