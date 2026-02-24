"""
Overlay module for the Speech-to-Text Engine.

This module creates a system overlay window that displays visual feedback
during speech recognition.
"""

import logging
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk
import os
import sys

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Overlay:
    """Creates a system overlay window for visual feedback."""

    def __init__(self, config: dict):
        """Initialize overlay with configuration."""
        self.config = config
        self.overlay_timeout = config.get('overlay_timeout', 3)
        self.root = None
        self.label = None
        self._visibility_lock = threading.Lock()
        self.is_visible = False
        self.is_running = False
        self.timeout_thread = None
        self.update_callback = None
        self.xdotool_available = config.get('xdotool_available', False)

    def create_overlay(self):
        """Create the overlay window."""
        if self.root:
            return

        # Create root window
        self.root = tk.Tk()
        self.root.title("Speech-to-Text Overlay")
        self.root.overrideredirect(True)  # Remove window decorations
        self.root.attributes('-topmost', True)  # Always on top
        self.root.attributes('-alpha', 0.8)  # Semi-transparent
        self.root.configure(bg='black')

        # Create label for text
        self.label = ttk.Label(
            self.root,
            text="",
            foreground="white",
            background="black",
            font=("Helvetica", self.config.get('overlay_font_size', 16))
        )
        self.label.pack(expand=True)

        # Set initial position
        self.update_position()

        # Hide initially
        self.root.withdraw()
        self.is_visible = False

    def update_position(self):
        """Update overlay position to be near cursor."""
        if not self.root:
            return

        try:
            # Get cursor position using xdotool if available
            if self.xdotool_available:
                result = subprocess.run(['xdotool', 'getmouselocation'], capture_output=True, text=True)
                if result.returncode == 0:
                    # Parse output: x:123 y:456 screen:0
                    parts = result.stdout.strip().split()
                    x_pos = int(parts[0].split(':')[1])
                    y_pos = int(parts[1].split(':')[1])

                    # Position overlay near cursor (slightly below)
                    self.root.geometry(f'+{x_pos}+{y_pos + 20}')
                    return

            # Fallback: position at center of screen
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.root.geometry(f'+{screen_width//2 - 100}+{screen_height//2 - 50}')
            logger.warning("Using fallback position for overlay")

        except Exception as e:
            logger.warning(f"Could not get cursor position: {e}")
            # Fallback: position at center of screen
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.root.geometry(f'+{screen_width//2 - 100}+{screen_height//2 - 50}')

    def update_state(self, state: str):
        """Thread-safe: schedule a label update on the Tk event loop."""
        if self.root and self.is_running:
            self.root.after(0, self._do_update_state, state)

    def _do_update_state(self, state: str):
        """Must only be called from the Tk thread (via root.after)."""
        if not self.root:
            return
        self.label.config(text=state)
        with self._visibility_lock:
            already_visible = self.is_visible
            if not already_visible:
                self.is_visible = True
        if not already_visible:
            self.update_position()
            self.root.deiconify()
            self._start_timeout()

    def _start_timeout(self):
        """Start auto-hide timer (called from Tk thread)."""
        if self.timeout_thread and self.timeout_thread.is_alive():
            return
        self.timeout_thread = threading.Thread(target=self._timeout_handler)
        self.timeout_thread.daemon = True
        self.timeout_thread.start()

    def _timeout_handler(self):
        """Sleep then schedule hide back on the Tk thread."""
        time.sleep(self.overlay_timeout)
        if self.root and self.is_running:
            self.root.after(0, self._do_hide)

    def _do_hide(self):
        """Must only be called from the Tk thread (via root.after)."""
        with self._visibility_lock:
            if self.is_visible:
                self.is_visible = False
                self.root.withdraw()

    def start(self):
        """Start the overlay system."""
        self.is_running = True
        self._tk_ready = threading.Event()

        # Tk must be created and driven entirely from one thread
        self.tk_thread = threading.Thread(target=self._run_tkinter, name="tk-overlay")
        self.tk_thread.daemon = True
        self.tk_thread.start()

        # Wait until the window is ready before returning
        self._tk_ready.wait(timeout=5)
        logger.info("Overlay system started")

    def _run_tkinter(self):
        """Create the Tk window and run its event loop — all in this thread."""
        try:
            self.create_overlay()
            self._tk_ready.set()
            self.root.mainloop()
        except Exception as e:
            logger.error("Tkinter error: %s", e)
            self._tk_ready.set()  # unblock start() even on failure

    def stop(self):
        """Stop the overlay system."""
        self.is_running = False
        if self.root:
            self.root.after(0, self.root.quit)
        logger.info("Overlay system stopped")

    def set_overlay_callback(self, callback: callable):
        """Set callback function to update overlay state."""
        self.update_callback = callback