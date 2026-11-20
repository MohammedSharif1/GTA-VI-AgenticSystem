"""9:16 vertical reframing and smart crop."""

from pathlib import Path
import subprocess
import shutil


def reframe_9_16(input_path: str, output_path: str, x_offset_ratio: float = 0.5) -> str:
    """
    Reframes 16:9 footage to 1080x1920 (9:16) vertical video.
    x_offset_ratio: 0.5 for center crop, <0.5 for left HUD focus, >0.5 for right focus.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in system PATH.")

    in_p = Path(input_path)
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Scale to height 1920, then crop width to 1080 centered at x_offset_ratio
    filter_complex = (
        f"scale=-1:1920,"
        f"crop=1080:1920:(in_w-1080)*{x_offset_ratio}:0"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(in_p),
        "-vf", filter_complex,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "copy",
        str(out_p)
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg reframe failed: {result.stderr}")

    return str(out_p)
