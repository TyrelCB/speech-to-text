"""
Audio capture module for the Speech-to-Text Engine.

This module handles microphone audio capture using PipeWire and detects hotkey events
using X11 (XGrabKey) on X11 sessions or evdev on Wayland sessions.
"""

import logging
import select
import subprocess
import threading
import time
import os
import sys
from typing import Callable, Optional

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Optional X11 libraries (not needed on Wayland)
try:
    from Xlib import X, display
    xlib_available = True
except ImportError:
    xlib_available = False

# Optional evdev library (needed on Wayland)
try:
    import evdev
    from evdev import ecodes
    evdev_available = True
except ImportError:
    evdev_available = False

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
        self.evdev_available = evdev_available
        self.setup_hotkey()

    def setup_hotkey(self):
        """Set up hotkey detection (evdev on Wayland, XGrabKey on X11)."""
        if self.config.get('wayland'):
            if not self.evdev_available:
                logger.error(
                    "evdev library not found. Install with: pip install evdev. "
                    "Hotkey detection disabled."
                )
                return
            target = self._detect_hotkey_evdev
            logger.info("Hotkey detection set up for: %s (evdev/Wayland)", self.hotkey)
        else:
            if not self.xlib_available:
                logger.warning("Hotkey detection disabled: X11 libraries not available")
                return
            # Parse X11 modifier masks
            try:
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
            except Exception as e:
                logger.error("Failed to parse hotkey: %s", e)
                return
            target = self._detect_hotkey_x11
            logger.info("Hotkey detection set up for: %s (X11)", self.hotkey)

        self.hotkey_thread = threading.Thread(target=target)
        self.hotkey_thread.daemon = True
        self.hotkey_thread.start()

    def _detect_hotkey_x11(self):
        """Background thread: X11 hotkey detection via XGrabKey."""
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

    def _detect_hotkey_evdev(self):
        """Background thread: Wayland hotkey detection via kernel evdev events."""
        # Map config modifier names to (left_keycode, right_keycode) pairs
        MODIFIER_MAP = {
            'ctrl':  (ecodes.KEY_LEFTCTRL,  ecodes.KEY_RIGHTCTRL),
            'shift': (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT),
            'alt':   (ecodes.KEY_LEFTALT,   ecodes.KEY_RIGHTALT),
            'meta':  (ecodes.KEY_LEFTMETA,  ecodes.KEY_RIGHTMETA),
            'super': (ecodes.KEY_LEFTMETA,  ecodes.KEY_RIGHTMETA),
        }

        parts = [p.lower() for p in self.hotkey.split('+')]
        modifier_pairs = []
        main_keycode = None

        for part in parts:
            if part in MODIFIER_MAP:
                modifier_pairs.append(MODIFIER_MAP[part])
            else:
                evdev_name = f'KEY_{part.upper()}'
                code = getattr(ecodes, evdev_name, None)
                if code is None:
                    logger.error("Unknown key '%s' in hotkey '%s'", part, self.hotkey)
                    return
                main_keycode = code

        if main_keycode is None:
            logger.error("No main key found in hotkey: %s", self.hotkey)
            return

        all_modifier_codes = {code for pair in modifier_pairs for code in pair}

        # Find readable keyboard devices
        keyboards = []
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                caps = dev.capabilities()
                if ecodes.EV_KEY in caps and ecodes.KEY_A in caps[ecodes.EV_KEY]:
                    keyboards.append(dev)
            except PermissionError:
                logger.warning(
                    "No permission to read %s — add yourself to the 'input' group: "
                    "sudo usermod -aG input $USER  (then log out and back in)", path
                )
            except Exception:
                pass

        if not keyboards:
            logger.error(
                "No keyboard devices accessible. "
                "Add yourself to the 'input' group: sudo usermod -aG input $USER"
            )
            return

        logger.info(
            "Monitoring %d keyboard device(s) for hotkey: %s (evdev)",
            len(keyboards), self.hotkey
        )

        modifier_state = set()

        while True:
            try:
                # select() with timeout so we can react to new devices in future
                rlist, _, _ = select.select(keyboards, [], [], 1.0)
                for dev in rlist:
                    for event in dev.read():
                        if event.type != ecodes.EV_KEY:
                            continue

                        code = event.code
                        state = event.value  # 0=up, 1=down, 2=auto-repeat

                        # Track modifier keys
                        if code in all_modifier_codes:
                            if state > 0:
                                modifier_state.add(code)
                            else:
                                modifier_state.discard(code)

                        # Handle the main key (ignore auto-repeat — real up/down only)
                        if code == main_keycode and state != 2:
                            modifiers_ok = all(
                                l in modifier_state or r in modifier_state
                                for l, r in modifier_pairs
                            )
                            if state == 1 and modifiers_ok:
                                self.hotkey_pressed = True
                                with self._capture_lock:
                                    capturing = self.is_capturing
                                if not capturing:
                                    self.start_capture()
                            elif state == 0:
                                # Stop on key-up regardless of current modifier state
                                self.hotkey_pressed = False
                                with self._capture_lock:
                                    capturing = self.is_capturing
                                if capturing:
                                    self.stop_capture()
            except Exception as e:
                logger.error("Error in evdev event loop: %s", e)
                time.sleep(0.1)

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