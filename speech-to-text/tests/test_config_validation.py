"""Tests for config schema validation."""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import validate_config


def _base_config():
    return {
        'hotkey': 'Ctrl+Shift+M',
        'model_size': 'small',
        'audio_chunk_duration': 5,
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
