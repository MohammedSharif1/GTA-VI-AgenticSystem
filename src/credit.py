"""On-screen source credit overlay.

R4 requires an on-screen credit on every short. Two details matter more than
they look:

* The text is passed via ``textfile=`` rather than ``text=``. Inline drawtext
  text has to survive FFmpeg's filter parser, which treats ``:``, ``,``, ``'``
  and ``%`` as syntax, so a creator name containing a colon previously produced
  a filter error or silently wrong output. A file sidesteps that entirely and
  also handles Arabic text with no escaping.
* The font is resolved to a real file (see ``src.fonts``) because the static
  Windows FFmpeg builds carry no fontconfig and cannot resolve a font by name.
"""

import tempfile
from pathlib import Path

from src.ffmpeg_tools import MediaInfo, probe_media, run_ffmpeg
from src.fonts import ffmpeg_font_path, resolve_font

DEFAULT_FONT_SIZE = 38
DEFAULT_BOX_OPACITY = 0.55
DEFAULT_TOP_MARGIN_PCT = 12.0
DEFAULT_VIDEO_HEIGHT = 1920

AUDIO_CODEC_ARGS = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]

ROCKSTAR_NAMES = {
    "rockstar",
    "rockstar games",
    "official",
    "rockstar games official",
}


def generate_credit_text(creator_name: str, channel_url: str | None = None) -> str:
    """Build the on-screen credit line for a source."""
    name = (creator_name or "").strip()
    if not name:
        return "Source: unknown creator"
    if name.lower() in ROCKSTAR_NAMES:
        return "Source: Rockstar Games"
    handle = _handle_from_url(channel_url)
    if handle and handle.lower() not in name.lower():
        return f"Source: {name} ({handle})"
    return f"Source: {name}"


def _handle_from_url(channel_url: str | None) -> str | None:
    if not channel_url:
        return None
    for segment in str(channel_url).rstrip("/").split("/"):
        if segment.startswith("@") and len(segment) > 1:
            return segment
    return None


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:")


def build_drawtext_filter(
    font_file: Path,
    text_file: Path,
    font_size: int,
    top_margin_pct: float,
    video_height: int,
    box_opacity: float,
) -> str:
    """Assemble the drawtext filter for a credit banner."""
    y = int(round(video_height * (top_margin_pct / 100.0)))
    return (
        f"drawtext=fontfile='{ffmpeg_font_path(font_file)}'"
        f":textfile='{_escape_filter_path(text_file)}'"
        f":fontcolor=white:fontsize={font_size}"
        f":box=1:boxcolor=black@{box_opacity:.2f}:boxborderw=14"
        f":x=(w-text_w)/2:y={y}"
    )


def burn_credit_overlay(
    input_path: str,
    output_path: str,
    credit_text: str,
    font_size: int = DEFAULT_FONT_SIZE,
    top_margin_pct: float = DEFAULT_TOP_MARGIN_PCT,
    video_height: int = DEFAULT_VIDEO_HEIGHT,
    box_opacity: float = DEFAULT_BOX_OPACITY,
) -> MediaInfo:
    """Burn ``credit_text`` into the top safe zone of ``input_path``."""
    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source}")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    font_file = resolve_font()
    with tempfile.TemporaryDirectory(prefix="findfeed-credit-") as temp_dir:
        text_file = Path(temp_dir) / "credit.txt"
        text_file.write_text(credit_text, encoding="utf-8")

        drawtext = build_drawtext_filter(
            font_file=font_file,
            text_file=text_file,
            font_size=font_size,
            top_margin_pct=top_margin_pct,
            video_height=video_height,
            box_opacity=box_opacity,
        )

        args = [
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            drawtext,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            *AUDIO_CODEC_ARGS,
            "-movflags",
            "+faststart",
            str(destination),
        ]
        run_ffmpeg(args, "Burning the source credit")

    return probe_media(destination)
