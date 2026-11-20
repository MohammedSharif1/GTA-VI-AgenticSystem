"""9:16 vertical reframing.

The previous implementation scaled to a fixed height and then cropped, which
breaks for sources narrower than the target after scaling (``in_w - 1080``
becomes negative and FFmpeg is asked to crop outside the frame). Scaling with
``force_original_aspect_ratio=increase`` guarantees the intermediate frame
covers 1080x1920 for any input aspect ratio, so the crop is always in bounds.
"""

from pathlib import Path

from src.ffmpeg_tools import MediaInfo, MediaToolError, probe_media, run_ffmpeg

DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920

# Quality settings for the vertical master. The final platform encodes are
# produced by the platforms themselves, so this is a high-quality intermediate.
VIDEO_CODEC_ARGS = [
    "-c:v",
    "libx264",
    "-preset",
    "medium",
    "-crf",
    "18",
    "-pix_fmt",
    "yuv420p",
]

AUDIO_CODEC_ARGS = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


class ReframeError(ValueError):
    """Raised when reframing parameters are invalid."""


def build_filter(width: int, height: int, x_offset_ratio: float) -> str:
    """Build the scale+crop filter chain.

    ``x_offset_ratio`` selects the crop column: 0.0 keeps the left edge, 0.5
    centres, 1.0 keeps the right edge. Useful for keeping a HUD or a character
    in frame instead of always cropping the middle.
    """
    ratio = min(max(x_offset_ratio, 0.0), 1.0)
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height}:(in_w-{width})*{ratio:.4f}:0,"
        "setsar=1"
    )


def reframe_9_16(
    input_path: str,
    output_path: str,
    x_offset_ratio: float = 0.5,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> MediaInfo:
    """Reframe ``input_path`` into a ``width``x``height`` vertical file."""
    if width <= 0 or height <= 0:
        raise ReframeError(f"Invalid target size {width}x{height}.")
    if width % 2 or height % 2:
        raise ReframeError(
            f"Target size {width}x{height} must be even on both axes for H.264."
        )

    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source}")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    args = [
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        build_filter(width, height, x_offset_ratio),
        *VIDEO_CODEC_ARGS,
        *AUDIO_CODEC_ARGS,
        "-movflags",
        "+faststart",
        str(destination),
    ]

    run_ffmpeg(args, f"Reframing to {width}x{height}")
    return verify_dimensions(destination, width, height)


def verify_dimensions(path: Path, width: int, height: int) -> MediaInfo:
    """Probe the output and assert the expected frame size."""
    info = probe_media(path)
    if (info.width, info.height) != (width, height):
        raise MediaToolError(
            f"Reframe produced {info.width}x{info.height}, expected "
            f"{width}x{height} ({path})."
        )
    return info
