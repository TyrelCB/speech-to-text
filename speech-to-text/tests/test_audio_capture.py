"""Tests for audio_capture module."""

import subprocess
import sys
import os
import threading
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_capture(config=None):
    """Create an AudioCapture with hotkey setup disabled."""
    from audio_capture import AudioCapture
    if config is None:
        config = {'hotkey': 'Ctrl+Shift+M', 'audio_buffer_size': 1024}
    with patch.object(AudioCapture, 'setup_hotkey'):
        return AudioCapture(config)


def test_timeout_expired_is_caught():
    """stop_capture must survive TimeoutExpired without leaking is_capturing=True."""
    ac = _make_capture()
    ac.is_capturing = True

    mock_proc = MagicMock()
    mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd='pw-record', timeout=5), None]
    ac.process = mock_proc

    ac.stop_capture()

    assert not ac.is_capturing, "is_capturing must be False after stop_capture"
    mock_proc.kill.assert_called_once()


def test_stop_capture_kills_on_timeout():
    """process.kill() must be called when wait() times out."""
    ac = _make_capture()
    ac.is_capturing = True

    mock_proc = MagicMock()
    mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd='pw-record', timeout=5), None]
    ac.process = mock_proc

    ac.stop_capture()

    mock_proc.kill.assert_called_once()
    assert mock_proc.wait.call_count == 2


def test_process_audio_uses_bytearray():
    """_process_audio internal buffer must use bytearray (not bytes concatenation)."""
    import audio_capture
    import inspect
    src = inspect.getsource(audio_capture.AudioCapture._process_audio)
    assert 'bytearray' in src, "_process_audio must use bytearray for efficient buffering"
    assert 'buffer +=' not in src, "_process_audio must not use bytes += (O(n²) copies)"


def test_stop_event_used_in_process_audio():
    """_process_audio must check _stop_event, not is_capturing directly."""
    import audio_capture
    import inspect
    src = inspect.getsource(audio_capture.AudioCapture._process_audio)
    assert '_stop_event' in src, "_process_audio must use self._stop_event for clean shutdown"
