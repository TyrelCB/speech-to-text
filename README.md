# Speech-to-Text Engine

A Linux speech-to-text engine that captures audio via hotkey and transcribes it to text at the cursor location.

## Features

- Hotkey-activated microphone capture (`hold` or `toggle` mode)
- Real-time speech transcription using Whisper
- System overlay with visual feedback
- Text output at cursor location using xdotool

## Installation

Install or update everything with one command:

```bash
curl -fsSL https://raw.githubusercontent.com/TyrelCB/speech-to-text/master/install.sh | sh
```

The installer will:

- install the supported system packages it needs (`git`, `python`, `xdotool`, `wtype`, PipeWire tools, Tk)
- install `uv` if it is missing
- clone or update the repo into `~/.local/share/speech-to-text`
- create or refresh `.venv`
- install PyTorch with an explicit backend instead of relying on the default PyPI `torch` wheel
- offer an optional setup wizard to choose CPU/GPU preference and benchmark Whisper models with a measured recommendation
- create or update `~/.config/systemd/user/speech-to-text.service`
- reload and enable the user service when `systemctl --user` is reachable

Optional overrides:

```bash
curl -fsSL https://raw.githubusercontent.com/TyrelCB/speech-to-text/master/install.sh | \
  INSTALL_DIR="$HOME/speech-to-text" sh
```

Force a specific PyTorch backend during install:

```bash
curl -fsSL https://raw.githubusercontent.com/TyrelCB/speech-to-text/master/install.sh | \
  TORCH_BACKEND=cu130 sh
```

For unattended installs, skip the prompt explicitly:

```bash
curl -fsSL https://raw.githubusercontent.com/TyrelCB/speech-to-text/master/install.sh | \
  INTERACTIVE_SETUP=never sh
```

If you prefer to install manually:

1. Install uv (Python package manager):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Create and activate a virtual environment:
   ```bash
   uv venv --seed
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   uv pip install -r requirements.txt
   uv pip install torch --torch-backend=auto
   ```

   On DGX Spark / GB10, prefer:
   ```bash
   uv pip install torch --torch-backend=cu130
   ```

4. Install required system tools:

   **Fedora/RHEL:**
   ```bash
   sudo dnf install xdotool wtype pipewire-utils python3-tkinter
   ```
   **Debian/Ubuntu:**
   ```bash
   sudo apt install xdotool wtype pipewire-bin python3-tk
   ```
   If `pipewire-bin` is unavailable on your release, install `pipewire` instead.
   **Arch Linux:**
   ```bash
   sudo pacman -S xdotool wtype pipewire tk
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
- device_preference: `auto`, `cpu`, or `gpu`
- audio_chunk_duration: Duration of audio chunks for processing (seconds)
- max_record_seconds: Maximum recording duration before auto-stop (seconds)
- overlay_timeout: Time before overlay auto-hides (seconds)
- audio_buffer_size: Size of audio buffer (samples)

Prefer putting machine-specific overrides in `config.local.json`. The installer setup wizard writes `model_size` and `device_preference` there so future `git pull` updates can still fast-forward cleanly.

You can rerun the setup wizard later with:

```bash
.venv/bin/python setup_wizard.py
```

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

The installer already creates or updates the unit file for you. If you want to manage it manually:

1. Copy the unit file and update the path if you did not install to `~/.local/share/speech-to-text`:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp speech-to-text.service ~/.config/systemd/user/
   # The service file uses %h/.local/share/speech-to-text by default.
   # Edit the file if you cloned the repo elsewhere:
   # WorkingDirectory=%h/your/path/to/speech-to-text
   # ExecStart=%h/your/path/to/speech-to-text/.venv/bin/python %h/your/path/to/speech-to-text/main.py
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
