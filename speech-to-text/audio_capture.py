"""
Audio capture module for the Speech-to-Text Engine.

This module handles microphone audio capture using PipeWire and detects hotkey events
using X11 event listeners.
"""

import logging
import subprocess
import threading
import time
import os
import sys
from typing import Callable, Optional

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import X11 libraries for hotkey detection
try:
    from Xlib import X, display
    from Xlib.ext import record
    from Xlib.protocol import rq
    import Xlib.ext.xtest
    xlib_available = True
except ImportError:
    logging.warning("X11 libraries not available. Hotkey detection will not work.")
    xlib_available = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AudioCapture:
    """Handles audio capture from microphone using PipeWire."""

    def __init__(self, config: dict):
        """Initialize audio capture with configuration."""
        self.config = config
        self.hotkey = config.get('hotkey', 'Ctrl+Shift+M')
        self.audio_buffer_size = config.get('audio_buffer_size', 1024)
        self._capture_lock = threading.Lock()
        self.is_capturing = False
        self._stop_event = threading.Event()
        self.callback: Optional[Callable] = None
        self.process = None
        self.hotkey_thread = None
        self.hotkey_pressed = False
        self.xlib_available = xlib_available
        self.setup_hotkey()

    def setup_hotkey(self):
        """Set up hotkey detection using X11."""
        if not self.xlib_available:
            logger.warning("Hotkey detection is disabled due to missing X11 libraries")
            return

        try:
            # Parse hotkey string
            key_parts = self.hotkey.split('+')
            self.modifier_keys = []
            self.main_key = None

            for part in key_parts:
                if part == 'Ctrl':
                    self.modifier_keys.append(X.ControlMask)
                elif part == 'Shift':
                    self.modifier_keys.append(X.ShiftMask)
                elif part == 'Alt':
                    self.modifier_keys.append(X.Mod1Mask)
                elif part == 'Meta':
                    self.modifier_keys.append(X.Mod4Mask)
                else:
                    self.main_key = part

            if not self.main_key:
                logger.error("Could not parse hotkey: %s", self.hotkey)
                return

            # Start hotkey detection thread
            self.hotkey_thread = threading.Thread(target=self._detect_hotkey)
            self.hotkey_thread.daemon = True
            self.hotkey_thread.start()

            logger.info("Hotkey detection set up for: %s", self.hotkey)

        except Exception as e:
            logger.error("Failed to set up hotkey detection: %s", str(e))

    def _detect_hotkey(self):
        """Background thread to detect hotkey events."""
        if not self.xlib_available:
            logger.warning("Hotkey detection cannot run: X11 libraries not available")
            return

        try:
            # Get the display
            d = display.Display()
            root = d.screen().root

            # Create a context for recording
            ctx = d.record_create_context(
                0,
                [record.AllClients],
                [{
                    'core_requests': (0, 0),
                    'core_replies': (0, 0),
                    'ext_requests': (0, 0, 0, 0),
                    'ext_replies': (0, 0, 0, 0),
                    'delivered_events': (0, 0),
                    'device_events': (X.KeyReleaseMask, X.KeyPressMask),
                    'errors': (0, 0),
                    'client_started': False,
                    'client_died': False,
                }]
            )

            # Enable recording
            d.record_enable_context(ctx, self._process_event)

            # Enter main loop
            while True:
                time.sleep(0.1)

        except Exception as e:
            logger.error("Hotkey detection failed: %s", str(e))

    def _process_event(self, reply):
        """Process X11 events for hotkey detection."""
        if not self.xlib_available:
            return

        if reply.category != record.FromServer:
            return
        if reply.client_swapped:
            return
        if not len(reply.data) or ord(reply.data[0]) < 2:
            return

        data = reply.data
        while len(data):
            event, data = rq.EventField(None).parse_binary_value(data, d.display), data[1:]

            if event.type == X.KeyPress:
                # Check if hotkey is pressed
                if self._is_hotkey_pressed(event):
                    self.hotkey_pressed = True
                    if not self.is_capturing:
                        self.start_capture()

            elif event.type == X.KeyRelease:
                # Check if hotkey is released
                if self._is_hotkey_pressed(event):
                    self.hotkey_pressed = False
                    if self.is_capturing:
                        self.stop_capture()

    def _resolve_keycode(self, key_name: str):
        """Resolve a key name to an X11 keycode using the actual keyboard layout."""
        if not self.xlib_available:
            return None
        try:
            import Xlib.XK as XK
            d = display.Display()
            # Try the key name as-is, then lowercase, then uppercase
            for candidate in (key_name, key_name.lower(), key_name.upper()):
                keysym = XK.string_to_keysym(candidate)
                if keysym != 0:
                    keycode = d.keysym_to_keycode(keysym)
                    if keycode != 0:
                        return keycode
            return None
        except Exception as e:
            logger.warning("Could not resolve keycode for '%s': %s", key_name, e)
            return None

    def _is_hotkey_pressed(self, event):
        """Check if the current event matches the hotkey."""
        if not self.xlib_available:
            return False

        try:
            # Get the key code from the event
            key_code = event.detail

            # Get the state (modifier keys)
            state = event.state

            # Check if main key matches
            # This is a simplified implementation - in practice, we'd need to map key names to key codes
            # For now, we'll just use the key code directly

            # This is a placeholder - in a real implementation, we'd map the key name to a key code
            # For example, if hotkey is 'M', we'd need to find the key code for 'M'
            # This requires a keymap lookup which is complex

            # For simplicity, we'll just return True when the main key is pressed
            # In a real implementation, we'd need to use Xlib to get the keymap and find the key code

            # This is a placeholder implementation
            # We'll assume that when the key code matches the expected key code for our main key
            # we've detected the hotkey

            # For now, we'll just return True if the modifiers match and the key code is non-zero
            # This is not a complete implementation but sufficient for demonstration

            # Check modifiers
            modifiers_match = True
            for modifier in self.modifier_keys:
                if not (state & modifier):
                    modifiers_match = False
                    break

            # Resolve the expected keycode for the main key using the actual keymap
            main_key_code = self._resolve_keycode(self.main_key)
            if main_key_code is None:
                logger.warning("Unknown key in hotkey: %s", self.main_key)
                return False

            # Check if the key code matches and modifiers match
            return (key_code == main_key_code) and modifiers_match

        except Exception as e:
            logger.error("Error in _is_hotkey_pressed: %s", str(e))
            return False

    def start_capture(self):
        """Start audio capture."""
        with self._capture_lock:
            if self.is_capturing:
                return

            logger.info("Starting audio capture...")

            self._stop_event.clear()
            # Start PipeWire recording
            # This will record to stdout
            self.process = subprocess.Popen([
                'pw-record',
                '--format', 'wav',
                '--target', 'pipe:1',
                '--rate', str(self.config.get('audio_sample_rate', 16000)),
                '--channels', str(self.config.get('audio_channels', 1))
            ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

            self.is_capturing = True

        # Start audio processing thread
        self.audio_thread = threading.Thread(target=self._process_audio)
        self.audio_thread.daemon = True
        self.audio_thread.start()

    def _process_audio(self):
        """Process audio data from PipeWire."""
        buffer = bytearray()
        chunk_bytes = (
            self.config.get('audio_chunk_duration', 5)
            * self.config.get('audio_sample_rate', 16000)
            * 2  # 16-bit = 2 bytes per sample
            * self.config.get('audio_channels', 1)
        )

        try:
            while not self._stop_event.is_set() and self.process:
                data = self.process.stdout.read(self.audio_buffer_size)
                if data:
                    buffer.extend(data)

                    if len(buffer) >= chunk_bytes:
                        if self.callback:
                            self.callback(bytes(buffer))
                        buffer.clear()

                # Check if process is still running
                if self.process.poll() is not None:
                    break

        except Exception as e:
            logger.error("Error processing audio: %s", str(e))

    def stop_capture(self):
        """Stop audio capture."""
        with self._capture_lock:
            if not self.is_capturing:
                return
            logger.info("Stopping audio capture...")
            self._stop_event.set()

        # Stop the process
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("pw-record did not terminate, killing")
                self.process.kill()
                self.process.wait()
            finally:
                self.process = None

        with self._capture_lock:
            self.is_capturing = False

    def start(self):
        """Start the audio capture system."""
        logger.info("Audio capture system started")

    def stop(self):
        """Stop the audio capture system."""
        self.stop_capture()

    def set_callback(self, callback: Callable):
        """Set callback function to be called with audio data."""
        self.callback = callback