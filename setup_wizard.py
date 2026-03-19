"""
Interactive setup helper for install-time device and model selection.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from typing import Any

from app_config import DEFAULT_CONFIG, VALID_MODEL_SIZES, load_config

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_CONFIG_PATH = os.path.join(CONFIG_DIR, "config.local.json")
MODEL_ORDER = ["tiny", "base", "small", "medium", "large"]
MODEL_RANK = {name: index for index, name in enumerate(MODEL_ORDER)}


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        reply = input(f"{prompt} {suffix} ").strip().lower()
        if not reply:
            return default
        if reply in {"y", "yes"}:
            return True
        if reply in {"n", "no"}:
            return False
        print("Please answer y or n.")


def prompt_choice(prompt: str, options: list[str], default: str) -> str:
    option_map = {str(index): option for index, option in enumerate(options, start=1)}

    print(prompt)
    for index, option in enumerate(options, start=1):
        marker = " (default)" if option == default else ""
        print(f"  {index}. {option}{marker}")

    while True:
        reply = input("> ").strip().lower()
        if not reply:
            return default
        if reply in option_map:
            return option_map[reply]
        if reply in options:
            return reply
        print(f"Enter a number 1-{len(options)} or one of: {', '.join(options)}")


def detect_runtime_gpu() -> tuple[bool, str | None]:
    try:
        import torch
    except ImportError:
        return False, None

    if not torch.cuda.is_available():
        return False, None

    device_name = None
    try:
        device_name = torch.cuda.get_device_name(0)
    except Exception:
        device_name = "CUDA GPU"
    return True, device_name


def resolve_device(preference: str, gpu_available: bool) -> str:
    preference = str(preference).lower()
    if preference == "cpu":
        return "cpu"
    if preference == "gpu":
        return "cuda" if gpu_available else "cpu"
    return "cuda" if gpu_available else "cpu"


def recommended_model_for_device(device: str) -> str:
    return "small" if device == "cuda" else "base"


def load_local_overrides() -> dict[str, Any]:
    try:
        with open(LOCAL_CONFIG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_local_overrides(overrides: dict[str, Any]):
    with open(LOCAL_CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(overrides, handle, indent=2, sort_keys=True)
        handle.write("\n")


def record_sample(duration_seconds: int, config: dict[str, Any]) -> bytes:
    process = subprocess.Popen(
        [
            "pw-record",
            "--format",
            "s16",
            "--rate",
            str(config.get("audio_sample_rate", DEFAULT_CONFIG["audio_sample_rate"])),
            "--channels",
            str(config.get("audio_channels", DEFAULT_CONFIG["audio_channels"])),
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    if process.stdout is None:
        raise RuntimeError("pw-record did not provide a stdout stream")

    captured = bytearray()

    def _reader():
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                return
            captured.extend(chunk)

    reader_thread = threading.Thread(target=_reader, name="setup-wizard-recorder", daemon=True)
    reader_thread.start()

    try:
        time.sleep(duration_seconds)
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    finally:
        reader_thread.join(timeout=5)

    return bytes(captured)


def benchmark_models(
    audio_data: bytes, models: list[str], device: str, language: str
) -> list[dict[str, Any]]:
    import numpy as np
    import whisper

    try:
        import torch
    except ImportError:
        torch = None

    audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
    results: list[dict[str, Any]] = []

    for model_name in models:
        print(f"\nBenchmarking model '{model_name}' on {device}...")
        load_start = time.perf_counter()
        model = whisper.load_model(model_name, device=device)
        load_elapsed = time.perf_counter() - load_start

        transcribe_start = time.perf_counter()
        result = model.transcribe(
            audio_array,
            language=language,
            condition_on_previous_text=False,
        )
        transcribe_elapsed = time.perf_counter() - transcribe_start

        results.append(
            {
                "model_size": model_name,
                "load_seconds": load_elapsed,
                "transcribe_seconds": transcribe_elapsed,
                "text": result.get("text", "").strip(),
            }
        )

        del model
        if torch is not None and device == "cuda":
            torch.cuda.empty_cache()

    return results


def recommend_model_from_benchmark(
    results: list[dict[str, Any]], fallback_model: str
) -> tuple[str, str | None]:
    if not results:
        return fallback_model, None

    valid_results = [result for result in results if result["model_size"] in MODEL_RANK]
    if not valid_results:
        return fallback_model, None

    fastest = min(result["transcribe_seconds"] for result in valid_results)
    tolerance = max(0.05, fastest * 0.15)
    eligible = [
        result
        for result in valid_results
        if result["transcribe_seconds"] <= fastest + tolerance
    ]
    eligible.sort(
        key=lambda result: (
            MODEL_RANK[result["model_size"]],
            -result["transcribe_seconds"],
            -result["load_seconds"],
        )
    )
    recommended = eligible[-1]
    fastest_result = min(
        valid_results,
        key=lambda result: (result["transcribe_seconds"], MODEL_RANK[result["model_size"]]),
    )

    if recommended["model_size"] == fastest_result["model_size"]:
        reason = "fastest transcription in the benchmark"
    else:
        delta = recommended["transcribe_seconds"] - fastest
        reason = (
            f"within {delta:.1f}s of the fastest result and a larger model "
            f"than {fastest_result['model_size']}"
        )

    return recommended["model_size"], reason


def run_benchmark(config: dict[str, Any], actual_device: str, default_model: str) -> str | None:
    if not shutil_which("pw-record"):
        print("Skipping benchmark: pw-record is not installed.")
        return None

    if not prompt_yes_no("Record a short sample and compare models now?", default=False):
        return None

    print("Press Enter, then speak for 5 seconds.")
    input()
    print("Recording now...")
    audio_data = record_sample(5, config)
    if not audio_data:
        print("No audio was captured. Keeping the recommended model.")
        return None

    candidate_models = ["tiny", "base", "small"]
    if actual_device == "cuda":
        candidate_models.append("medium")

    print(
        "Running benchmark. Models may download the first time, so the load step can take a while."
    )

    try:
        results = benchmark_models(
            audio_data=audio_data,
            models=candidate_models,
            device=actual_device,
            language=str(config.get("language", DEFAULT_CONFIG["language"])),
        )
    except Exception as exc:
        print(f"Benchmark failed: {exc}")
        return None

    print("\nBenchmark results:")
    for result in results:
        preview = result["text"] or "<no text>"
        print(
            f"  {result['model_size']}: load {result['load_seconds']:.1f}s, "
            f"transcribe {result['transcribe_seconds']:.1f}s"
        )
        print(f"     {preview}")

    choices = [result["model_size"] for result in results]
    benchmark_default, reason = recommend_model_from_benchmark(results, default_model)
    if benchmark_default not in choices:
        benchmark_default = default_model if default_model in choices else choices[0]
        reason = None

    if reason:
        print(f"\nRecommended from benchmark: {benchmark_default} ({reason})")
    else:
        print(f"\nRecommended from benchmark: {benchmark_default}")
    return prompt_choice("Choose the model to keep:", choices, benchmark_default)


def shutil_which(command: str) -> str | None:
    import shutil

    return shutil.which(command)


def main() -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Setup wizard requires an interactive terminal.")
        return 1

    config = load_config(CONFIG_DIR)
    local_overrides = load_local_overrides()
    gpu_available, gpu_name = detect_runtime_gpu()
    existing_device_preference = str(
        config.get("device_preference", DEFAULT_CONFIG["device_preference"])
    ).lower()

    print("Speech-to-Text setup")
    print("")
    if gpu_available:
        print(f"GPU detected and usable by Torch: {gpu_name}")
        device_options = ["auto", "gpu", "cpu"]
        device_default = (
            existing_device_preference
            if "device_preference" in local_overrides and existing_device_preference in device_options
            else DEFAULT_CONFIG["device_preference"]
        )
        device_preference = prompt_choice(
            "Choose which compute device you prefer:",
            device_options,
            device_default,
        )
    else:
        print("No Torch-usable GPU detected. Speech recognition will run on CPU.")
        device_preference = "cpu"

    actual_device = resolve_device(device_preference, gpu_available)
    recommended_model = recommended_model_for_device(actual_device)
    current_model = str(config.get("model_size", DEFAULT_CONFIG["model_size"])).lower()
    if current_model not in VALID_MODEL_SIZES:
        current_model = recommended_model

    model_default = (
        current_model
        if "model_size" in local_overrides and current_model in VALID_MODEL_SIZES
        else recommended_model
    )

    print("")
    selected_model = run_benchmark(config, actual_device, model_default)
    if selected_model is None:
        model_options = ["tiny", "base", "small", "medium", "large"]
        print(
            f"Recommended model for {actual_device}: {recommended_model}"
        )
        selected_model = prompt_choice(
            "Choose the Whisper model size:",
            model_options,
            model_default,
        )

    overrides = load_local_overrides()
    overrides["device_preference"] = device_preference
    overrides["model_size"] = selected_model
    save_local_overrides(overrides)

    print("")
    print(f"Saved overrides to {LOCAL_CONFIG_PATH}")
    print(f"  device_preference: {device_preference}")
    print(f"  model_size: {selected_model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
