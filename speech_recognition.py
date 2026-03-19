"""
Speech recognition module for the Speech-to-Text Engine.

This module uses Whisper (OpenAI) for speech recognition and processes audio chunks
in real-time.
"""

import logging
import os
import sys
import numpy as np
import torch
from typing import Callable, Optional

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import Whisper
try:
    import whisper
    whisper_available = True
except ImportError:
    logging.error("Whisper library not installed. Please install openai-whisper package.")
    whisper_available = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def resolve_torch_device(device_preference: str, cuda_available: bool) -> str:
    """Map config preference to the actual Torch device string."""
    normalized = str(device_preference).lower()
    if normalized == "cpu":
        return "cpu"
    if normalized == "gpu":
        return "cuda" if cuda_available else "cpu"
    return "cuda" if cuda_available else "cpu"


class SpeechRecognition:
    """Handles speech recognition using Whisper."""

    def __init__(self, config: dict):
        """Initialize speech recognition with configuration."""
        self.config = config
        self.model_size = config.get('model_size', 'small')
        self.device_preference = str(config.get('device_preference', 'auto')).lower()
        self.callback: Optional[Callable] = None
        self.overlay_callback: Optional[Callable] = None
        self.model = None
        cuda_available = torch.cuda.is_available()
        self.device = resolve_torch_device(self.device_preference, cuda_available)
        if self.device_preference == "gpu" and not cuda_available:
            logger.warning("GPU was requested but CUDA is unavailable; falling back to CPU")
        self.whisper_available = whisper_available
        if not self.whisper_available:
            logger.error("Whisper is not available. Speech recognition will not work.")
            return
        self.load_model()

    def load_model(self):
        """Load Whisper model."""
        if not self.whisper_available:
            logger.error("Cannot load Whisper model: library not available")
            return

        logger.info(
            "Loading Whisper %s model on %s (preference: %s)...",
            self.model_size,
            self.device,
            self.device_preference,
        )
        try:
            self.model = whisper.load_model(self.model_size, device=self.device)
            logger.info(f"Whisper {self.model_size} model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise

    def process_audio(self, audio_data: bytes):
        """Process audio data using Whisper."""
        if not self.whisper_available:
            logger.error("Cannot process audio: Whisper library not available")
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

            # Transcribe audio
            result = self.model.transcribe(
                audio_array,
                language=self.config.get('language', 'en'),
                condition_on_previous_text=False,
            )
            text = result["text"].strip()

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
