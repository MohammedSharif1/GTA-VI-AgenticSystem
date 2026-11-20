"""Transcription and subtitle generation using Whisper API."""

import os
from pathlib import Path
from typing import List, Dict, Any


def transcribe_audio_whisper(audio_or_video_path: str, api_key: str = None) -> Dict[str, Any]:
    """
    Transcribes audio using OpenAI Whisper API.
    Returns transcript with detected language and segments with timestamps.
    """
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found. Set in .env or pass explicitly.")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    path = Path(audio_or_video_path)
    with open(path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"]
        )

    return response.model_dump()


def generate_srt(segments: List[Dict[str, Any]], output_path: str) -> str:
    """Generates standard SRT file from timestamped segments."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    def format_ts(seconds: float) -> str:
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    lines = []
    for idx, seg in enumerate(segments, start=1):
        start = format_ts(seg["start"])
        end = format_ts(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{idx}\n{start} --> {end}\n{text}\n")

    content = "\n".join(lines)
    with open(out_p, "w", encoding="utf-8") as f:
        f.write(content)

    return str(out_p)
