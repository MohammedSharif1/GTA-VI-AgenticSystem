"""Technical QA for a rendered short.

QA answers questions the pipeline can actually measure: right size, right
length, audio present or absent exactly as intended. It deliberately does not
claim to verify editorial quality, claim-to-footage accuracy, or that the credit
banner is legible. Those need a human, and a green QA report is not publication
clearance.
"""

from dataclasses import dataclass, field
from pathlib import Path

from src.ffmpeg_tools import MediaInfo, MediaToolError, probe_media

MIN_DURATION_SECONDS = 1.0
EXPECTED_ASPECT_TOLERANCE = 0.01


@dataclass(frozen=True)
class Check:
    """One QA check and its outcome."""

    name: str
    passed: bool
    detail: str


@dataclass
class QaReport:
    """Collection of QA checks for one rendered file."""

    path: str
    info: MediaInfo | None = None
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(Check(name=name, passed=passed, detail=detail))

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if not check.passed]

    @property
    def passed(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        if self.passed:
            return f"QA passed ({len(self.checks)} checks) for {self.path}"
        lines = [f"QA failed for {self.path}:"]
        lines.extend(f"  - {c.name}: {c.detail}" for c in self.failures)
        return "\n".join(lines)


def run_qa(
    path: Path | str,
    expected_width: int,
    expected_height: int,
    max_duration_seconds: float,
    expect_audio: bool,
    frame_budget_seconds: float | None = None,
) -> QaReport:
    """Run technical checks on a rendered file and return the report.

    ``expect_audio=False`` is used when R10 forced a mute, which makes a
    surviving audio stream a failure rather than a warning.
    """
    target = Path(path)
    report = QaReport(path=str(target))

    if not target.is_file():
        report.add("file_exists", False, f"File not found: {target}")
        return report
    report.add("file_exists", True, "File present")

    size_bytes = target.stat().st_size
    if size_bytes == 0:
        report.add("non_empty", False, "File is zero bytes")
        return report
    report.add("non_empty", True, f"{size_bytes} bytes")

    try:
        info = probe_media(target)
    except MediaToolError as exc:
        report.add("probeable", False, str(exc))
        return report
    report.info = info
    report.add("probeable", True, info.describe())

    report.add(
        "has_video",
        info.has_video,
        f"video codec={info.video_codec or 'none'}",
    )

    report.add(
        "dimensions",
        (info.width, info.height) == (expected_width, expected_height),
        f"{info.width}x{info.height}, expected {expected_width}x{expected_height}",
    )

    aspect = info.width / info.height if info.height else 0.0
    expected_aspect = expected_width / expected_height
    report.add(
        "aspect_ratio",
        abs(aspect - expected_aspect) <= EXPECTED_ASPECT_TOLERANCE,
        f"aspect {aspect:.4f}, expected {expected_aspect:.4f}",
    )

    report.add(
        "duration",
        MIN_DURATION_SECONDS <= info.duration_seconds <= max_duration_seconds,
        f"{info.duration_seconds:.2f}s, allowed "
        f"{MIN_DURATION_SECONDS:.1f}s-{max_duration_seconds:.1f}s",
    )

    if frame_budget_seconds is not None:
        report.add(
            "source_excerpt_limit",
            info.duration_seconds <= frame_budget_seconds,
            f"{info.duration_seconds:.2f}s against source-excerpt limit "
            f"{frame_budget_seconds:.0f}s (R2)",
        )

    if expect_audio:
        report.add(
            "audio_present",
            info.has_audio,
            f"audio codec={info.audio_codec or 'none'} (audio should be kept)",
        )
    else:
        report.add(
            "audio_muted",
            not info.has_audio,
            "no audio stream (R10 mute enforced)"
            if not info.has_audio
            else f"audio stream still present: {info.audio_codec}",
        )

    report.add(
        "even_dimensions",
        info.width % 2 == 0 and info.height % 2 == 0,
        f"{info.width}x{info.height} must be even for H.264",
    )

    return report
