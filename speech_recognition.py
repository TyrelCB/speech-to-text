"""
Speech recognition module for the Speech-to-Text Engine.

This module uses faster-whisper (CTranslate2 backend) for speech recognition and
processes audio chunks in real-time.
"""

import logging
import os
import sys
import numpy as np
from typing import Callable, Optional

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import faster-whisper
try:
    from faster_whisper import WhisperModel
    whisper_available = True
except ImportError:
    logging.error("faster-whisper not installed. Please install the faster-whisper package.")
    whisper_available = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cuda_device_count() -> int:
    """Return the number of CUDA devices visible to CTranslate2, or 0."""
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def resolve_device(device_preference: str, cuda_available: bool) -> str:
    """Map config preference to the actual CTranslate2 device string."""
    normalized = str(device_preference).lower()
    if normalized == "cpu":
        return "cpu"
    if normalized == "gpu":
        return "cuda" if cuda_available else "cpu"
    return "cuda" if cuda_available else "cpu"


def compute_type_for_device(device: str) -> str:
    """Pick a memory-efficient compute type for the resolved device."""
    return "float16" if device == "cuda" else "int8"


class SpeechRecognition:
    """Handles speech recognition using faster-whisper."""

    def __init__(self, config: dict):
        """Initialize speech recognition with configuration."""
        self.config = config
        self.model_size = config.get('model_size', 'small')
        self.device_preference = str(config.get('device_preference', 'auto')).lower()
        self.callback: Optional[Callable] = None
        self.overlay_callback: Optional[Callable] = None
        self.model = None
        cuda_available = cuda_device_count() > 0
        self.device = resolve_device(self.device_preference, cuda_available)
        self.compute_type = compute_type_for_device(self.device)
        if self.device_preference == "gpu" and not cuda_available:
            logger.warning("GPU was requested but no CUDA device is available; falling back to CPU")
        self.whisper_available = whisper_available
        if not self.whisper_available:
            logger.error("faster-whisper is not available. Speech recognition will not work.")
            return
        self.load_model()

    def load_model(self):
        """Load the faster-whisper model."""
        if not self.whisper_available:
            logger.error("Cannot load model: faster-whisper not available")
            return

        logger.info(
            "Loading Whisper %s model on %s (compute_type=%s, preference: %s)...",
            self.model_size,
            self.device,
            self.compute_type,
            self.device_preference,
        )
        try:
            # Prefer the locally cached weights so a running service never
            # depends on network access. On the very first run the model is not
            # cached yet, so fall back to downloading it once.
            try:
                self.model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                    local_files_only=True,
                )
            except Exception:
                logger.info("Model not cached locally; downloading %s once...", self.model_size)
                self.model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                    local_files_only=False,
                )
            logger.info(f"Whisper {self.model_size} model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

    def process_audio(self, audio_data: bytes):
        """Process audio data using faster-whisper."""
        if not self.whisper_available:
            logger.error("Cannot process audio: faster-whisper not available")
            if self.overlay_callback:
                self.overlay_callback("Error: Whisper not available")
            return

        if not self.model:
            logger.error("Whisper model not loaded")
            if self.overlay_callback:
                self.overlay_callback("Error: Model not loaded")
            return

        try:
            # Update overlay state
            if self.overlay_callback:
                self.overlay_callback("Transcribing...")

            # Convert bytes to numpy array
            # Audio is 16-bit mono at 16kHz
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            # Transcribe audio. faster-whisper returns a generator of segments
            # that is consumed lazily, so we join their text.
            segments, _info = self.model.transcribe(
                audio_array,
                language=self.config.get('language', 'en'),
                condition_on_previous_text=False,
            )
            text = "".join(segment.text for segment in segments).strip()

            # Update overlay state
            if self.overlay_callback:
                self.overlay_callback("Listening...")

            # Send text to output
            if self.callback:
                self.callback(text)

        except Exception as e:
            logger.error(f"Error in speech recognition: {e}")
            # Update overlay state to show error
            if self.overlay_callback:
                self.overlay_callback("Error: Transcription failed")

    def set_callback(self, callback: Callable):
        """Set callback function to be called with transcribed text."""
        self.callback = callback

    def set_overlay_callback(self, callback: Callable):
        """Set callback function to update overlay state."""
        self.overlay_callback = callback
