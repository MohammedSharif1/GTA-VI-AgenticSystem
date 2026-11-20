"""FFmpeg/FFprobe discovery, invocation, and media probing.

Every media stage goes through here. Three things this centralises:

1. Binary discovery. On Windows a fresh WinGet install has not updated the
   PATH of already-running shells, so a bare ``ffmpeg`` lookup fails even
   though the tool is installed. ``FFMPEG_BINARY`` / ``FFPROBE_BINARY``
   override everything; otherwise PATH is tried, then common install roots.
2. Failure reporting. FFmpeg writes the real cause deep in stderr, so the
   raised error carries the tail of stderr instead of a bare exit code.
3. Probing. QA needs duration, dimensions, and whether an audio stream
   survived, without shelling out to ffprobe in four different modules.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

FFMPEG_ENV_VAR = "FFMPEG_BINARY"
FFPROBE_ENV_VAR = "FFPROBE_BINARY"

_STDERR_TAIL_LINES = 20
_PROBE_TIMEOUT_SECONDS = 120
_RENDER_TIMEOUT_SECONDS = 3600


class MediaToolError(RuntimeError):
    """Raised when a media binary is missing or an FFmpeg command fails."""


@dataclass(frozen=True)
class MediaInfo:
    """Facts about a media file that the pipeline needs in order to decide."""

    path: str
    duration_seconds: float
    width: int
    height: int
    has_video: bool
    has_audio: bool
    video_codec: str
    audio_codec: str
    fps: float

    @property
    def aspect_ratio(self) -> float:
        if self.height == 0:
            return 0.0
        return self.width / self.height

    def describe(self) -> str:
        audio = self.audio_codec if self.has_audio else "none"
        return (
            f"{self.width}x{self.height} @ {self.fps:.2f}fps, "
            f"{self.duration_seconds:.2f}s, video={self.video_codec or 'none'}, "
            f"audio={audio}"
        )


def _windows_search_roots() -> list[Path]:
    roots: list[Path] = []
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        roots.append(Path(local_appdata) / "Microsoft" / "WinGet" / "Packages")
    userprofile = os.getenv("USERPROFILE")
    if userprofile:
        roots.append(Path(userprofile) / "scoop" / "shims")
    programdata = os.getenv("PROGRAMDATA")
    if programdata:
        roots.append(Path(programdata) / "chocolatey" / "bin")
    roots.append(Path("C:/ffmpeg/bin"))
    return roots


def _search_install_roots(binary_name: str) -> str | None:
    """Look for a binary under known package-manager install roots."""
    if os.name != "nt":
        return None
    for root in _windows_search_roots():
        if not root.is_dir():
            continue
        direct = root / binary_name
        if direct.is_file():
            return str(direct)
        try:
            # WinGet extracts into a versioned subdirectory.
            for candidate in root.rglob(binary_name):
                if candidate.is_file():
                    return str(candidate)
        except OSError:
            continue
    return None


@lru_cache(maxsize=None)
def find_binary(tool: str) -> str:
    """Resolve ``ffmpeg`` or ``ffprobe`` to an absolute path."""
    if tool not in ("ffmpeg", "ffprobe"):
        raise MediaToolError(f"Unsupported media tool requested: {tool}")

    env_var = FFMPEG_ENV_VAR if tool == "ffmpeg" else FFPROBE_ENV_VAR
    override = os.getenv(env_var)
    if override:
        override_path = Path(override).expanduser()
        if not override_path.is_file():
            raise MediaToolError(f"{env_var} points at a missing file: {override_path}")
        return str(override_path)

    on_path = shutil.which(tool)
    if on_path:
        return on_path

    searched = _search_install_roots(tool + (".exe" if os.name == "nt" else ""))
    if searched:
        return searched

    raise MediaToolError(
        f"{tool} was not found. Install FFmpeg and either add it to PATH or set "
        f"{env_var} to the full path of the {tool} executable."
    )


def ffmpeg_binary() -> str:
    return find_binary("ffmpeg")


def ffprobe_binary() -> str:
    return find_binary("ffprobe")


def tool_versions() -> dict[str, str]:
    """Version banner recorded in the run log."""
    versions: dict[str, str] = {}
    for tool in ("ffmpeg", "ffprobe"):
        try:
            result = subprocess.run(
                [find_binary(tool), "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,
            )
        except (MediaToolError, subprocess.SubprocessError):
            versions[tool] = "unavailable"
            continue
        lines = result.stdout.splitlines()
        versions[tool] = lines[0].strip() if lines else "unknown"
    return versions


def _stderr_tail(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return "\n".join(lines[-_STDERR_TAIL_LINES:])


def run_ffmpeg(args: list[str], action: str) -> None:
    """Run FFmpeg with ``args`` and raise a readable error on failure."""
    command = [ffmpeg_binary(), "-hide_banner", "-loglevel", "error", *args]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=_RENDER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaToolError(
            f"{action} timed out after {_RENDER_TIMEOUT_SECONDS}s."
        ) from exc

    if result.returncode != 0:
        raise MediaToolError(f"{action} failed:\n{_stderr_tail(result.stderr)}")


def _to_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _parse_fps(value: str | None) -> float:
    if not value:
        return 0.0
    numerator, _, denominator = value.partition("/")
    top = _to_float(numerator)
    bottom = _to_float(denominator) if denominator else 1.0
    if bottom == 0:
        return 0.0
    return top / bottom


def probe_media(path: Path | str) -> MediaInfo:
    """Read duration, dimensions, and stream presence for a media file."""
    media_path = Path(path)
    if not media_path.is_file():
        raise MediaToolError(f"Cannot probe missing file: {media_path}")

    command = [
        ffprobe_binary(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(media_path),
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaToolError(f"ffprobe timed out on {media_path}") from exc

    if result.returncode != 0:
        raise MediaToolError(
            f"ffprobe failed on {media_path}:\n{_stderr_tail(result.stderr)}"
        )

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise MediaToolError(
            f"ffprobe returned unreadable JSON for {media_path}"
        ) from exc

    streams = payload.get("streams") or []
    video_stream = next(
        (s for s in streams if s.get("codec_type") == "video"), None
    )
    audio_stream = next(
        (s for s in streams if s.get("codec_type") == "audio"), None
    )

    duration = _to_float((payload.get("format") or {}).get("duration"))
    if duration <= 0 and video_stream:
        duration = _to_float(video_stream.get("duration"))

    return MediaInfo(
        path=str(media_path),
        duration_seconds=duration,
        width=int(video_stream.get("width") or 0) if video_stream else 0,
        height=int(video_stream.get("height") or 0) if video_stream else 0,
        has_video=video_stream is not None,
        has_audio=audio_stream is not None,
        video_codec=str((video_stream or {}).get("codec_name") or ""),
        audio_codec=str((audio_stream or {}).get("codec_name") or ""),
        fps=_parse_fps((video_stream or {}).get("avg_frame_rate")),
    )
