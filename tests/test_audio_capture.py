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


def test_session_buffer_is_bytearray():
    """AudioCapture must store session audio in a bytearray for efficient buffering."""
    ac = _make_capture()
    assert isinstance(ac._session_buffer, bytearray)


def test_process_audio_avoids_bytes_concat():
    """_process_audio must avoid bytes += concatenation (O(n²) copies)."""
    import audio_capture
    import inspect
    src = inspect.getsource(audio_capture.AudioCapture._process_audio)
    assert 'buffer +=' not in src, "_process_audio must not use bytes += (O(n²) copies)"


def test_stop_event_used_in_process_audio():
    """_process_audio must check _stop_event, not is_capturing directly."""
    import audio_capture
    import inspect
    src = inspect.getsource(audio_capture.AudioCapture._process_audio)
    assert '_stop_event' in src, "_process_audio must use self._stop_event for clean shutdown"


def test_calculate_audio_level_normalized():
    """_calculate_audio_level should return a 0.0-1.0 normalized value."""
    ac = _make_capture()

    assert ac._calculate_audio_level(b"") == 0.0
    assert ac._calculate_audio_level((0).to_bytes(2, "little", signed=True)) == 0.0
    level = ac._calculate_audio_level((32767).to_bytes(2, "little", signed=True))
    assert 0.99 <= level <= 1.0


def test_stop_capture_cancels_max_record_timer():
    """stop_capture must cancel any active max-record timer."""
    ac = _make_capture({'hotkey': 'Ctrl+Shift+M', 'audio_buffer_size': 1024, 'max_record_seconds': 600})
    ac.is_capturing = True
    ac.process = MagicMock()
    timer = MagicMock()
    ac._max_record_timer = timer

    ac.stop_capture()

    timer.cancel.assert_called_once()
    assert ac._max_record_timer is None
