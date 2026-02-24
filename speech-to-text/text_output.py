"""
Text output module for the Speech-to-Text Engine.

This module uses xdotool to simulate keyboard input and send transcribed text
at the cursor location.
"""

import logging
import subprocess
import os
import sys
from typing import Callable, Optional

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextOutput:
    """Handles text output using xdotool."""

    def __init__(self, config: dict):
        """Initialize text output with configuration."""
        self.config = config
        self.callback: Optional[Callable] = None
        self.last_text = ""
        self.wayland = config.get('wayland', False)
        self.xdotool_available = config.get('xdotool_available', False)
        self.wtype_available = config.get('wtype_available', False)

    def send_text(self, text: str):
        """Send text to the active window."""
        if not text:
            return

        if self.wayland and not self.wtype_available:
            logger.error("Cannot send text: wtype not available on Wayland")
            return

        if not self.wayland and not self.xdotool_available:
            logger.error("Cannot send text: xdotool not available")
            return

        try:
            # Format text for better output
            formatted_text = self._format_text(text)

            # Send text as keystrokes
            self._send_keystrokes(formatted_text)

            # Log the output
            logger.info(f"Sent text: {formatted_text}")

        except Exception as e:
            logger.error(f"Error sending text: {e}")

    def _format_text(self, text: str) -> str:
        """Format text with proper punctuation spacing and capitalization."""
        # Remove extra whitespace
        text = ' '.join(text.split())

        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]

        # Add period at end if no punctuation
        if text and text[-1] not in '.!?':
            text += '.'

        # Add a trailing separator so consecutive transcriptions do not run together.
        if text:
            text += ' '

        return text

    def _send_keystrokes(self, text: str):
        """Send text as keystrokes using wtype (Wayland) or xdotool (X11)."""
        if self.wayland:
            try:
                subprocess.run(['wtype', '--', text], check=True)
            except subprocess.CalledProcessError as e:
                logger.error("wtype failed: %s", e)
        else:
            try:
                subprocess.run(
                    ['xdotool', 'type', '--clearmodifiers', '--', text],
                    check=True
                )
            except subprocess.CalledProcessError as e:
                logger.error("xdotool type failed: %s", e)

    def set_callback(self, callback: Callable):
        """Set callback function to be called with text to output."""
        self.callback = callback
