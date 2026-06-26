"""
MCP Server wrapper for the Speech-to-Text Engine.

This provides an HTTP/SSE endpoint that exposes the speech-to-text
transcription results via MCP tools, so Hermes can query recent
transcriptions or get notified of new ones.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from mcp.server.fastmcp import FastMCP

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global state for recent transcriptions
transcription_buffer: list[dict] = []
MAX_BUFFER = 100
last_transcription_time: float = 0
last_transcription_text: str = ""

# File path for persistent storage
TRANSCRIPTION_LOG = Path(__file__).parent / "transcriptions.jsonl"


def load_existing_transcriptions() -> list[dict]:
    """Load any existing transcriptions from the log file."""
    if TRANSCRIPTION_LOG.exists():
        try:
            with open(TRANSCRIPTION_LOG, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            transcription_buffer.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception as e:
            logger.warning(f"Failed to load transcription log: {e}")
    return transcription_buffer


def save_transcription(text: str):
    """Save a transcription to the buffer and log file."""
    global last_transcription_time, last_transcription_text
    
    entry = {
        "text": text,
        "timestamp": datetime.now().isoformat(),
        "unix_time": time.time()
    }
    
    transcription_buffer.append(entry)
    last_transcription_time = time.time()
    last_transcription_text = text
    
    # Keep buffer manageable
    if len(transcription_buffer) > MAX_BUFFER:
        transcription_buffer = transcription_buffer[-MAX_BUFFER:]
    
    # Append to log file
    try:
        with open(TRANSCRIPTION_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning(f"Failed to save transcription: {e}")


# Create MCP server
mcp = FastMCP(
    "speech-to-text",
    instructions="Speech-to-Text Engine MCP Server. Provides access to live and historical transcriptions from the desktop speech recognition engine."
)


@mcp.tool()
def get_recent_transcriptions(count: int = 10) -> list[dict]:
    """
    Get the most recent transcriptions from the speech-to-text engine.
    
    Args:
        count: Number of recent transcriptions to return (default: 10, max: 100)
    
    Returns:
        List of transcription entries with text and timestamp
    """
    count = min(count, MAX_BUFFER)
    recent = list(reversed(transcription_buffer[-count:]))
    return recent


@mcp.tool()
def get_latest_transcription() -> Optional[dict]:
    """
    Get the most recent transcription.
    
    Returns:
        The latest transcription entry with text and timestamp, or None if none available
    """
    if not transcription_buffer:
        return None
    return transcription_buffer[-1]


@mcp.tool()
def get_transcription_since(unix_timestamp: float) -> list[dict]:
    """
    Get all transcriptions after a given Unix timestamp.
    
    Args:
        unix_timestamp: Get transcriptions after this time (seconds since epoch)
    
    Returns:
        List of transcription entries after the specified time
    """
    result = [t for t in transcription_buffer if t.get("unix_time", 0) > unix_timestamp]
    return result


@mcp.tool()
def clear_transcriptions() -> str:
    """
    Clear all in-memory transcriptions. The log file is preserved.
    
    Returns:
        Confirmation message with count of cleared entries
    """
    count = len(transcription_buffer)
    transcription_buffer.clear()
    return f"Cleared {count} transcriptions from memory. Log file preserved."


@mcp.tool()
def get_transcription_status() -> dict:
    """
    Get the current status of the speech-to-text engine.
    
    Returns:
        Status dictionary with buffer size, last transcription time, and uptime
    """
    return {
        "buffer_size": len(transcription_buffer),
        "last_transcription_time": last_transcription_time,
        "last_transcription_text": last_transcription_text[:100] if last_transcription_text else None,
        "log_file": str(TRANSCRIPTION_LOG),
        "log_exists": TRANSCRIPTION_LOG.exists(),
        "log_lines": sum(1 for _ in open(TRANSCRIPTION_LOG)) if TRANSCRIPTION_LOG.exists() else 0
    }


@mcp.tool()
def export_transcriptions(format: str = "json") -> str:
    """
    Export all transcriptions from the log file.
    
    Args:
        format: Output format - 'json' or 'text' (default: json)
    
    Returns:
        All transcriptions in the requested format
    """
    if not TRANSCRIPTION_LOG.exists():
        return "No transcription log found."
    
    try:
        entries = []
        with open(TRANSCRIPTION_LOG, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        
        if format == "text":
            return "\n".join([f"[{e.get('timestamp', 'unknown')}] {e.get('text', '')}" for e in entries])
        else:
            return json.dumps(entries, indent=2)
    except Exception as e:
        return f"Error exporting: {e}"


def update_transcription_callback(text: str):
    """Callback to receive transcriptions from the main engine."""
    if text and text.strip():
        save_transcription(text.strip())
        logger.info(f"MCP: Captured transcription: {text[:50]}...")


# Patch the main module's TextOutput to use our callback
def patch_text_output():
    """Patch the TextOutput class to also send data to MCP."""
    original_send_text = None
    
    try:
        from text_output import TextOutput
        original_send_text = TextOutput.send_text
        
        def patched_send_text(self, text: str):
            result = original_send_text(self, text)
            if text and text.strip():
                save_transcription(text.strip())
            return result
        
        TextOutput.send_text = patched_send_text
        logger.info("Patched TextOutput.send_text to also save transcriptions for MCP")
    except Exception as e:
        logger.warning(f"Could not patch TextOutput: {e}")


if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Speech-to-Text MCP Server")
    parser.add_argument("--http", action="store_true", help="Enable HTTP transport")
    parser.add_argument("--port", type=int, default=8100, help="Port to listen on")
    parser.add_argument("--sse", action="store_true", help="Use SSE transport")
    args = parser.parse_args()
    
    # Load existing transcriptions
    load_existing_transcriptions()
    logger.info(f"Loaded {len(transcription_buffer)} existing transcriptions")
    
    # Patch the text output to capture transcriptions
    patch_text_output()
    
    # Run the MCP server
    if args.http:
        import uvicorn
        from starlette.middleware.cors import CORSMiddleware
        
        mcp.settings.streamable_http_path = "/sse"
        mcp.settings.stateless_http = True
        # FastMCP defaults host to 127.0.0.1 and auto-enables DNS-rebinding
        # protection with an allowlist of only localhost/127.0.0.1/::1 Host
        # headers. We bind the socket to 0.0.0.0 below, so relax this too —
        # otherwise requests via any other hostname get 421 Invalid Host header.
        mcp.settings.transport_security.enable_dns_rebinding_protection = False
        mcp.settings.transport_security.allowed_hosts = ["*"]
        mcp.settings.transport_security.allowed_origins = ["*"]

        app = CORSMiddleware(
            mcp.streamable_http_app(),
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        logger.info(f"Starting MCP server at http://localhost:{args.port}/sse")
        uvicorn.run(app, host="0.0.0.0", port=args.port)
    else:
        logger.info("Starting MCP server via stdio")
        mcp.run()
