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
        """Background thread to detect hotkey events using XGrabKey."""
        if not self.xlib_available:
            logger.warning("Hotkey detection cannot run: X11 libraries not available")
            return

        try:
            self._xdisplay = display.Display()
            root = self._xdisplay.screen().root

            # Pre-resolve keycode once (avoids per-event display calls)
            main_keycode = self._resolve_keycode(self.main_key)
            if main_keycode is None:
                logger.error("Cannot resolve keycode for '%s'", self.main_key)
                return

            modifier_mask = 0
            for m in self.modifier_keys:
                modifier_mask |= m

            # Also grab with CapsLock/NumLock active so the hotkey works regardless
            lock_combos = [0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask]
            for extra in lock_combos:
                root.grab_key(
                    main_keycode,
                    modifier_mask | extra,
                    False,           # owner_events=False: key not forwarded to focused window
                    X.GrabModeAsync,
                    X.GrabModeAsync,
                )

            root.change_attributes(event_mask=X.KeyPressMask | X.KeyReleaseMask)
            self._xdisplay.flush()
            logger.info("Hotkey grabbed: %s (keycode %d)", self.hotkey, main_keycode)

            # Debounce timer for stop: X11 key auto-repeat fires repeated
            # KeyRelease+KeyPress pairs while a key is held.  We cancel any
            # pending stop whenever a fresh KeyPress arrives within the window.
            _AUTO_REPEAT_MS = 0.06   # 60 ms > typical repeat interval (~25 ms)
            _stop_timer = None

            def _schedule_stop():
                nonlocal _stop_timer
                if _stop_timer is not None:
                    _stop_timer.cancel()
                _stop_timer = threading.Timer(_AUTO_REPEAT_MS, self.stop_capture)
                _stop_timer.start()

            key_held = False
            while True:
                event = self._xdisplay.next_event()
                if event.type == X.KeyPress and event.detail == main_keycode:
                    # Cancel any pending debounced stop (auto-repeat case)
                    if _stop_timer is not None:
                        _stop_timer.cancel()
                        _stop_timer = None
                    if not key_held:
                        key_held = True
                        self.hotkey_pressed = True
                        with self._capture_lock:
                            capturing = self.is_capturing
                        if not capturing:
                            self.start_capture()
                elif event.type == X.KeyRelease and event.detail == main_keycode:
                    key_held = False
                    self.hotkey_pressed = False
                    _schedule_stop()

        except Exception as e:
            logger.error("Hotkey detection failed: %s", str(e))

    def _resolve_keycode(self, key_name: str):
        """Resolve a key name to an X11 keycode using the actual keyboard layout."""
        if not self.xlib_available or not hasattr(self, '_xdisplay'):
            return None
        try:
            import Xlib.XK as XK
            # Try the key name as-is, then lowercase, then uppercase
            for candidate in (key_name, key_name.lower(), key_name.upper()):
                keysym = XK.string_to_keysym(candidate)
                if keysym != 0:
                    keycode = self._xdisplay.keysym_to_keycode(keysym)
                    if keycode != 0:
                        return keycode
            return None
        except Exception as e:
            logger.warning("Could not resolve keycode for '%s': %s", key_name, e)
            return None

    def start_capture(self):
        """Start audio capture."""
        with self._capture_lock:
            if self.is_capturing:
                return

            logger.info("Starting audio capture...")

            self._stop_event.clear()
            # Record raw s16le PCM to stdout (no WAV header to strip)
            self.process = subprocess.Popen([
                'pw-record',
                '--format', 's16',
                '--rate', str(self.config.get('audio_sample_rate', 16000)),
                '--channels', str(self.config.get('audio_channels', 1)),
                '-'   # write to stdout
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
        finally:
            # Flush any remaining audio shorter than one full chunk
            if buffer and self.callback:
                logger.info("Flushing %d bytes of remaining audio", len(buffer))
                self.callback(bytes(buffer))

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