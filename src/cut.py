"""FFmpeg-based video excerpt cutting."""

from pathlib import Path
import subprocess
import shutil


def cut_excerpt(input_path: str, output_path: str, start_time: float, end_time: float) -> str:
    """
    Cuts video excerpt between start_time and end_time without re-encoding when possible,
    or with accurate frame seeks.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in system PATH. Install ffmpeg to run pipeline.")

    in_p = Path(input_path)
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    duration = end_time - start_time
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start_time),
        "-i", str(in_p),
        "-t", str(duration),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-strict", "experimental",
        str(out_p)
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg cut failed: {result.stderr}")

    return str(out_p)
