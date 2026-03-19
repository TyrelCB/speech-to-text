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


def test_recommend_model_from_benchmark_prefers_largest_model_near_fastest():
    recommended, reason = setup_wizard.recommend_model_from_benchmark(
        [
            {"model_size": "tiny", "load_seconds": 1.6, "transcribe_seconds": 1.0},
            {"model_size": "base", "load_seconds": 1.7, "transcribe_seconds": 0.2},
            {"model_size": "small", "load_seconds": 3.3, "transcribe_seconds": 0.2},
            {"model_size": "medium", "load_seconds": 31.6, "transcribe_seconds": 0.3},
        ],
        fallback_model="base",
    )

    assert recommended == "small"
    assert reason is not None
    assert "larger model" in reason


def test_recommend_model_from_benchmark_prefers_fastest_when_others_are_slower():
    recommended, reason = setup_wizard.recommend_model_from_benchmark(
        [
            {"model_size": "tiny", "load_seconds": 0.8, "transcribe_seconds": 0.4},
            {"model_size": "base", "load_seconds": 1.2, "transcribe_seconds": 0.8},
            {"model_size": "small", "load_seconds": 3.0, "transcribe_seconds": 1.6},
        ],
        fallback_model="base",
    )

    assert recommended == "tiny"
    assert reason == "fastest transcription in the benchmark"


def test_save_local_overrides_persists_values(tmp_path, monkeypatch):
    local_path = tmp_path / "config.local.json"
    monkeypatch.setattr(setup_wizard, "LOCAL_CONFIG_PATH", str(local_path))

    setup_wizard.save_local_overrides({"model_size": "base", "device_preference": "cpu"})

    stored = json.loads(local_path.read_text(encoding="utf-8"))
    assert stored == {"device_preference": "cpu", "model_size": "base"}
