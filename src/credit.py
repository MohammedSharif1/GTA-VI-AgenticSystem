"""Credit overlay and watermark generator."""

from pathlib import Path
import subprocess
import shutil


def generate_credit_text(creator_name: str) -> str:
    """Generates standard attribution string."""
    norm = creator_name.strip()
    if norm.lower() in ["rockstar", "rockstar games", "official"]:
        return "Source: Rockstar Games"
    return f"Source: {norm}"


def burn_credit_overlay(input_path: str, output_path: str, credit_text: str) -> str:
    """
    Burns non-intrusive credit banner at the top of the video within platform safe zones.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in system PATH.")

    in_p = Path(input_path)
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Escape text for ffmpeg drawtext filter
    escaped_text = credit_text.replace(":", "\\:").replace("'", "")

    drawtext_filter = (
        f"drawtext=text='{escaped_text}':"
        f"fontcolor=white:fontsize=36:"
        f"box=1:boxcolor=black@0.6:boxborderw=10:"
        f"x=(w-text_w)/2:y=240"  # Placed inside top safe zone (12% down from 1920)
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(in_p),
        "-vf", drawtext_filter,
        "-c:v", "libx264",
        "-c:a", "copy",
        str(out_p)
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg credit overlay failed: {result.stderr}")

    return str(out_p)
