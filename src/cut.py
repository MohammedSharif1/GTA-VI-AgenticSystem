"""Excerpt cutting with explicit audio handling.

R10 requires source audio to be muted when licensed radio music is audible.
That rule is enforced here as a real FFmpeg operation (``-an``), not as a form
field: if ``mute_audio`` is true the output has no audio stream at all, which
QA can verify afterwards.
"""

from pathlib import Path

from src.ffmpeg_tools import MediaInfo, MediaToolError, probe_media, run_ffmpeg

VIDEO_CODEC_ARGS = [
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-crf",
    "20",
    "-pix_fmt",
    "yuv420p",
]

AUDIO_CODEC_ARGS = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]

# Tolerated drift between the requested window and the rendered duration.
DURATION_TOLERANCE_SECONDS = 0.5


class CutError(ValueError):
    """Raised when a cut cannot be attempted with the supplied window."""


def cut_excerpt(
    input_path: str,
    output_path: str,
    start_time: float,
    end_time: float,
    mute_audio: bool = False,
) -> MediaInfo:
    """Cut ``[start_time, end_time]`` from ``input_path`` into ``output_path``.

    ``mute_audio`` drops the audio stream entirely (R10). The output is always
    re-encoded so the requested window is frame-accurate rather than snapped to
    the nearest keyframe, and so a source without an audio stream cannot break a
    later step.
    """
    start = float(start_time)
    end = float(end_time)
    if start < 0:
        raise CutError(f"start_time must not be negative, got {start:.2f}s.")
    if end <= start:
        raise CutError(
            f"end_time ({end:.2f}s) must be after start_time ({start:.2f}s)."
        )

    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source}")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    duration = end - start
    args = [
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:v:0",
        *VIDEO_CODEC_ARGS,
    ]

    if mute_audio:
        args.append("-an")
    else:
        args.extend(["-map", "0:a:0?", *AUDIO_CODEC_ARGS])

    args.extend(["-movflags", "+faststart", str(destination)])

    run_ffmpeg(args, f"Cutting excerpt {start:.2f}s-{end:.2f}s")

    info = probe_media(destination)
    if not info.has_video:
        raise MediaToolError(f"Cut produced no video stream: {destination}")

    drift = abs(info.duration_seconds - duration)
    if info.duration_seconds <= 0 or drift > DURATION_TOLERANCE_SECONDS:
        raise MediaToolError(
            f"Cut duration {info.duration_seconds:.2f}s does not match the "
            f"requested {duration:.2f}s window (tolerance "
            f"{DURATION_TOLERANCE_SECONDS}s)."
        )

    if mute_audio and info.has_audio:
        raise MediaToolError(
            f"Audio muting was requested but {destination} still has an audio "
            "stream. R10 is not satisfied."
        )

    return info
