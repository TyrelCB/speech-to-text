# speech-to-text

MCP server that transcribes audio and video files using [faster-whisper](https://github.com/SYSTRAN/faster-whisper), returning per-word timestamps.

## Features

- Word-level start/end timestamps and confidence scores
- Audio and video input (MP4, MKV, WAV, MP3, FLAC, M4A, and more)
- Automatic audio extraction from video via ffmpeg
- Optional transcript prompt to guide Whisper's output
- Configurable model size (tiny → large-v3)
- stdio and HTTP/SSE modes
- Idle timeout: automatically unloads the model from memory after inactivity

## Requirements

- Python 3.10+
- ffmpeg

## Installation

```bash
pip install -r requirements.txt
```

On Debian/Ubuntu with an externally-managed Python environment:
```bash
pip install --break-system-packages -r requirements.txt
```

Whisper model files are downloaded automatically on first use to `~/.cache/huggingface/hub/`.

## Usage

### stdio (for Claude Code / MCP clients)

```bash
python3 mcp_server.py
```

### HTTP/SSE

```bash
python3 mcp_server.py --http
python3 mcp_server.py --http --port 8100
python3 mcp_server.py --http --port 8100 --idle-timeout 60
```

The server exposes an SSE endpoint at `http://localhost:<port>/sse`.

**`--idle-timeout <seconds>`** — unload the Whisper model from memory after this many seconds of inactivity (default: `300`). The model reloads automatically on the next request. Pass `0` to disable.

### systemd (start at boot)

```bash
cp speech-to-text-mcp.service ~/.config/systemd/user/
systemctl --user enable --now speech-to-text-mcp
```

## Claude Code integration

Add to `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "speech-to-text": {
      "type": "sse",
      "url": "http://localhost:8100/sse"
    }
  }
}
```

## Tool: `transcribe_audio`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | string | required | Path to audio or video file |
| `transcript` | string | `null` | Optional prompt to guide Whisper (vocabulary, style) |
| `model_size` | string | `"base"` | `tiny`, `base`, `small`, `medium`, `large`, `large-v2`, `large-v3` |
| `language` | string | `null` | BCP-47 language code (e.g. `"en"`). Auto-detected if omitted. |

### Response

```json
{
  "status": "ok",
  "text": "Today I'm walking through the city.",
  "language": "en",
  "language_probability": 0.99,
  "duration": 5.944,
  "word_count": 7,
  "words": [
    { "word": "Today", "start": 0.64, "end": 0.86, "confidence": 0.98 },
    { "word": "I'm",   "start": 0.86, "end": 1.02, "confidence": 0.87 }
  ],
  "segments": [
    { "start": 0.0, "end": 5.2, "text": "Today I'm walking through the city." }
  ]
}
```

Errors return `{ "status": "error", "message": "..." }`.
