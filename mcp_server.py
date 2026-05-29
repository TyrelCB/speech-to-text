from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("speech-to-text")

_model_cache: dict = {}

VALID_MODELS = {"tiny", "base", "small", "medium", "large", "large-v2", "large-v3"}


def _get_model(model_size: str):
    from faster_whisper import WhisperModel

    key = (model_size, "cpu", "int8")
    if key not in _model_cache:
        _model_cache[key] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _model_cache[key]


def _extract_audio_to_wav(input_path: Path, tmp_dir: str) -> Path:
    out_wav = Path(tmp_dir) / "audio.wav"
    cmd = [
        "/usr/bin/ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(out_wav),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")
    return out_wav


@mcp.tool()
def transcribe_audio(
    file_path: str,
    transcript: Optional[str] = None,
    model_size: str = "base",
    language: Optional[str] = None,
) -> dict:
    """
    Transcribe an audio or video file using Whisper with word-level timestamps.

    Args:
        file_path:   Path to an audio file (wav, mp3, flac, m4a, ogg, etc.) or
                     video file (mp4, mkv, avi, mov, webm, etc.). Audio is
                     extracted from video automatically via ffmpeg.
        transcript:  Optional text passed to Whisper as initial_prompt to guide
                     vocabulary and transcription style. Does not force exact
                     word matching.
        model_size:  Whisper model size: tiny, base, small, medium, large,
                     large-v2, large-v3. Defaults to 'base'. Larger = more
                     accurate but slower. Model files are downloaded on first
                     use to ~/.cache/huggingface/hub/.
        language:    BCP-47 language code (e.g. 'en', 'fr', 'ja'). Auto-
                     detected if not provided.

    Returns:
        On success:
          {
            "status": "ok",
            "text": str,
            "language": str,
            "language_probability": float,
            "duration": float,
            "word_count": int,
            "words": [{"word": str, "start": float, "end": float, "confidence": float}, ...],
            "segments": [{"start": float, "end": float, "text": str}, ...]
          }
        On error:
          {"status": "error", "message": str}
    """
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}
    if not path.is_file():
        return {"status": "error", "message": f"Path is not a file: {file_path}"}
    if model_size not in VALID_MODELS:
        return {
            "status": "error",
            "message": f"Invalid model_size '{model_size}'. Valid options: {sorted(VALID_MODELS)}",
        }

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = _extract_audio_to_wav(path, tmp_dir)
            model = _get_model(model_size)

            segments_iter, info = model.transcribe(
                str(audio_path),
                language=language,
                initial_prompt=transcript,
                word_timestamps=True,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )

            words: list[dict] = []
            segments_out: list[dict] = []
            full_text_parts: list[str] = []

            # Consume the lazy generator inside the tempdir context
            for segment in segments_iter:
                text = segment.text.strip()
                full_text_parts.append(text)
                segments_out.append({
                    "start": round(segment.start, 3),
                    "end": round(segment.end, 3),
                    "text": text,
                })
                if segment.words:
                    for w in segment.words:
                        words.append({
                            "word": w.word.strip(),
                            "start": round(w.start, 3),
                            "end": round(w.end, 3),
                            "confidence": round(w.probability, 4),
                        })

    except RuntimeError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": f"Transcription failed: {e}"}

    return {
        "status": "ok",
        "text": " ".join(full_text_parts),
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "duration": round(info.duration, 3),
        "word_count": len(words),
        "words": words,
        "segments": segments_out,
    }


def _find_free_port(start: int = 8100) -> int:
    import socket
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
    raise RuntimeError("No free port found in range")


if __name__ == "__main__":
    import sys
    if "--http" in sys.argv:
        import uvicorn
        from starlette.middleware.cors import CORSMiddleware

        port_arg = sys.argv[sys.argv.index("--port") + 1] if "--port" in sys.argv else None
        port = int(port_arg) if port_arg else _find_free_port()

        mcp.settings.streamable_http_path = "/sse"
        mcp.settings.stateless_http = True

        app = CORSMiddleware(
            mcp.streamable_http_app(),
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        print(f"Starting MCP server at http://localhost:{port}/sse", flush=True)
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        mcp.run()
