# Speech-to-Text Engine

A Linux speech-to-text engine that captures audio via hotkey and transcribes it to text at the cursor location.

## Features

- Hotkey-activated microphone capture (`hold` or `toggle` mode)
- Real-time speech transcription using Whisper
- System overlay with visual feedback
- Text output at cursor location using xdotool

## Installation

1. Install uv (Python package manager):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   Or if you prefer using pip:
   ```bash
   pip install uv
   ```

2. Create and activate a virtual environment:
   ```bash
   uv venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   uv pip install -r requirements.txt
   ```

   Note: The openai-whisper package has been installed with the latest version (20250625) instead of the specific version 20231106 specified in requirements.txt, as the latest version resolves build issues and provides improved compatibility.

4. Ensure required system tools are installed:
   ```bash
   sudo dnf install xdotool
   ```

5. Run the application:
   ```bash
   python main.py
   ```

## Configuration

Edit `config.json` to customize:
- hotkey: The key combination to activate speech capture
- hotkey_mode: `hold` (press-and-hold) or `toggle` (press once to start, again to stop)
- model_size: Whisper model size (tiny, base, small, medium, large)
- audio_chunk_duration: Duration of audio chunks for processing (seconds)
- max_record_seconds: Maximum recording duration before auto-stop (seconds)
- overlay_timeout: Time before overlay auto-hides (seconds)
- audio_buffer_size: Size of audio buffer (samples)

## Usage

1. Launch the application
2. Press the hotkey (`Ctrl+Space` in the current config)
3. Speak clearly into the microphone
4. Press it again to stop recording (toggle mode) or release if using hold mode
5. Transcribed text will appear at your cursor location

## Troubleshooting

- If audio capture fails, verify PipeWire is running: `systemctl --user status pipewire`
- If xdotool doesn't work, ensure you're using X11 (not Wayland)
- If transcription is inaccurate, try a larger Whisper model

## Run as a systemd user service

1. Copy the unit file:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp speech-to-text.service ~/.config/systemd/user/
   ```

2. Reload and enable:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now speech-to-text.service
   ```

3. Check logs:
   ```bash
   journalctl --user -u speech-to-text.service -f
   ```

## License

MIT
