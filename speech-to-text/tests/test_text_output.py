"""Tests for text_output module."""

import subprocess
import sys
import os
from unittest.mock import patch, MagicMock

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_import_no_name_error():
    """Module must import without NameError (Optional was missing previously)."""
    import importlib
    import text_output
    importlib.reload(text_output)


def test_send_text_uses_single_xdotool_call():
    """send_text must invoke xdotool exactly once per call (not per character)."""
    from text_output import TextOutput

    config = {'xdotool_available': True}
    to = TextOutput(config)

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        to.send_text("hello world")

    assert mock_run.call_count == 1, (
        f"Expected 1 subprocess.run call, got {mock_run.call_count}"
    )
    cmd = mock_run.call_args[0][0]
    assert cmd[:3] == ['xdotool', 'type', '--clearmodifiers'], (
        f"Unexpected xdotool command: {cmd}"
    )


def test_send_text_noop_when_xdotool_unavailable():
    """send_text must not call subprocess when xdotool is unavailable."""
    from text_output import TextOutput

    config = {'xdotool_available': False}
    to = TextOutput(config)

    with patch('subprocess.run') as mock_run:
        to.send_text("hello")

    mock_run.assert_not_called()


def test_clearmodifiers_flag_present():
    """--clearmodifiers must be passed to prevent hotkey modifier bleed."""
    from text_output import TextOutput

    config = {'xdotool_available': True}
    to = TextOutput(config)

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        to.send_text("test")

    cmd = mock_run.call_args[0][0]
    assert '--clearmodifiers' in cmd


def test_send_text_adds_trailing_space_separator():
    """Typed text should end with a space to separate consecutive transcriptions."""
    from text_output import TextOutput

    config = {'xdotool_available': True}
    to = TextOutput(config)

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        to.send_text("hello world")

    cmd = mock_run.call_args[0][0]
    assert cmd[-1] == "Hello world. "
