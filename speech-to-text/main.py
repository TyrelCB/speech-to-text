"""
Main entry point for the Speech-to-Text Engine.

This script initializes all components and starts the main event loop.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import components with error handling
try:
    from audio_capture import AudioCapture
except ImportError as e:
    logging.error(f"Failed to import audio_capture: {e}")
    sys.exit(1)

try:
    from overlay import Overlay
except ImportError as e:
    logging.error(f"Failed to import overlay: {e}")
    sys.exit(1)

try:
    from speech_recognition import SpeechRecognition
except ImportError as e:
    logging.error(f"Failed to import speech_recognition: {e}")
    sys.exit(1)

try:
    from text_output import TextOutput
except ImportError as e:
    logging.error(f"Failed to import text_output: {e}")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _check_xdotool() -> bool:
    """Check if xdotool is available on this system."""
    try:
        result = subprocess.run(['xdotool', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("xdotool is available")
            return True
        logger.warning("xdotool not available. Text output and overlay positioning will not work.")
        return False
    except Exception as e:
        logger.warning("xdotool not available: %s", e)
        return False


VALID_MODEL_SIZES = {'tiny', 'base', 'small', 'medium', 'large'}


def validate_config(config: dict):
    """Validate config values; raise ValueError with a clear message on bad input."""
    model_size = config.get('model_size', 'small')
    if model_size not in VALID_MODEL_SIZES:
        raise ValueError(
            f"Invalid model_size '{model_size}'. Must be one of: {', '.join(sorted(VALID_MODEL_SIZES))}"
        )

    for int_key in ('audio_chunk_duration', 'audio_sample_rate', 'audio_channels',
                    'overlay_timeout', 'overlay_font_size', 'audio_buffer_size'):
        val = config.get(int_key)
        if val is not None and (not isinstance(val, int) or val <= 0):
            raise ValueError(f"Config key '{int_key}' must be a positive integer, got: {val!r}")

    hotkey = config.get('hotkey', '')
    if not isinstance(hotkey, str) or not hotkey:
        raise ValueError(f"Config key 'hotkey' must be a non-empty string, got: {hotkey!r}")


def load_config():
    """Load configuration from config.json file."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        return {
            "hotkey": "Ctrl+Shift+M",
            "model_size": "small",
            "audio_chunk_duration": 5,
            "overlay_timeout": 3,
            "audio_buffer_size": 1024
        }

def main():
    """Main application function."""
    logger.info("Starting Speech-to-Text Engine...")

    # Load and validate configuration
    config = load_config()
    try:
        validate_config(config)
    except ValueError as e:
        logger.error("Invalid configuration: %s", e)
        sys.exit(1)

    # Single xdotool check shared by all components
    config['xdotool_available'] = _check_xdotool()

    # Initialize components
    audio_capture = AudioCapture(config)
    overlay = Overlay(config)
    speech_recognition = SpeechRecognition(config)
    text_output = TextOutput(config)

    # Start audio capture in a separate thread
    _shutdown = threading.Event()
    audio_thread = threading.Thread(target=audio_capture.start, name="audio-capture")
    audio_thread.start()

    # Connect components
    audio_capture.set_callback(speech_recognition.process_audio)
    speech_recognition.set_callback(text_output.send_text)
    speech_recognition.set_overlay_callback(overlay.update_state)

    # Start the overlay
    overlay.start()

    logger.info("Speech-to-Text Engine started successfully")

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down Speech-to-Text Engine...")
        audio_capture.stop()
        audio_thread.join(timeout=10)
        if audio_thread.is_alive():
            logger.warning("Audio thread did not stop cleanly")
        overlay.stop()
        sys.exit(0)

if __name__ == "__main__":
    main()