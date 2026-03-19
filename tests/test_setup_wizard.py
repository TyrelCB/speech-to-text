"""Tests for the interactive setup wizard helpers."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import setup_wizard


def test_recommended_model_for_cpu():
    assert setup_wizard.recommended_model_for_device("cpu") == "base"


def test_recommended_model_for_cuda():
    assert setup_wizard.recommended_model_for_device("cuda") == "small"


def test_resolve_device_preference():
    assert setup_wizard.resolve_device("auto", gpu_available=False) == "cpu"
    assert setup_wizard.resolve_device("auto", gpu_available=True) == "cuda"
    assert setup_wizard.resolve_device("cpu", gpu_available=True) == "cpu"
    assert setup_wizard.resolve_device("gpu", gpu_available=True) == "cuda"
    assert setup_wizard.resolve_device("gpu", gpu_available=False) == "cpu"


def test_save_local_overrides_persists_values(tmp_path, monkeypatch):
    local_path = tmp_path / "config.local.json"
    monkeypatch.setattr(setup_wizard, "LOCAL_CONFIG_PATH", str(local_path))

    setup_wizard.save_local_overrides({"model_size": "base", "device_preference": "cpu"})

    stored = json.loads(local_path.read_text(encoding="utf-8"))
    assert stored == {"device_preference": "cpu", "model_size": "base"}
