"""Render orchestration: gates -> cut -> reframe -> credit -> QA.

Each stage reports an explicit status so the run log says what actually
happened. A render that finished but failed QA is ``QA_FAILED``, not
``SUCCESS``; a job waiting for a file is ``AWAITING_SOURCE``, not a failure.

``publish_clearance`` is written as ``False`` in every record. Rendering is not
publishing, and this module has no authority to grant either.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.credit import burn_credit_overlay, generate_credit_text
from src.cut import cut_excerpt
from src.ffmpeg_tools import MediaToolError, tool_versions
from src.gates import GateValidationError, is_music_audible, validate_job_gates
from src.paths import out_dir, runs_log_path
from src.policy import load_policy, tightest_platform
from src.qa import QaReport, run_qa
from src.reframe import reframe_9_16

STATUS_SUCCESS = "SUCCESS"
STATUS_QA_FAILED = "QA_FAILED"
STATUS_BLOCKED = "BLOCKED"
STATUS_AWAITING_SOURCE = "AWAITING_SOURCE_FILE"
STATUS_FAILED = "FAILED"
STATUS_PLANNED = "PLANNED"


@dataclass(frozen=True)
class StageResult:
    """Outcome of a single pipeline stage."""

    name: str
    status: str
    detail: str = ""
    output: str | None = None


@dataclass
class RenderResult:
    """Everything the operator needs to know about one render attempt."""

    job_id: str
    status: str
    audio_muted: bool = False
    output_path: str | None = None
    stages: list[StageResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    qa: QaReport | None = None
    error: str | None = None
    execution_seconds: float = 0.0

    def to_log(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status,
            "publish_clearance": False,
            "audio_muted": self.audio_muted,
            "execution_seconds": round(self.execution_seconds, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stages": [
                {"name": s.name, "status": s.status, "detail": s.detail}
                for s in self.stages
            ],
            "warnings": self.warnings,
        }
        if self.output_path:
            payload["output_file"] = self.output_path
        if self.error:
            payload["error"] = self.error
        if self.qa:
            payload["qa"] = {
                "passed": self.qa.passed,
                "failures": [
                    {"check": c.name, "detail": c.detail} for c in self.qa.failures
                ],
            }
        return payload


def append_run_log(payload: dict[str, Any]) -> Path:
    """Append one JSON line to the run log."""
    path = runs_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def render_job(job: dict[str, Any], dry_run: bool = False) -> RenderResult:
    """Render a single job and return the structured result."""
    job_id = str(job.get("id") or "unnamed-job")
    result = RenderResult(job_id=job_id, status=STATUS_PLANNED)

    try:
        report = validate_job_gates(job)
    except GateValidationError as exc:
        result.status = STATUS_BLOCKED
        result.error = "; ".join(exc.failures)
        result.stages.append(StageResult("gates", "blocked", result.error))
        append_run_log(result.to_log())
        return result

    # R10 is enforced downstream, not assumed: the flag decides the mute.
    result.audio_muted = is_music_audible(job)
    result.warnings.extend(report.warnings)
    result.stages.append(
        StageResult(
            "gates",
            "passed",
            f"{len(report.passed)} checks passed, {len(report.warnings)} warning(s)",
        )
    )

    source_file = job.get("source_file")
    if not source_file or not Path(str(source_file)).expanduser().is_file():
        result.status = STATUS_AWAITING_SOURCE
        result.error = f"Source file not available locally: {source_file!r}"
        result.stages.append(StageResult("source", "missing", result.error))
        append_run_log(result.to_log())
        return result

    source_path = Path(str(source_file)).expanduser()

    if dry_run:
        result.status = STATUS_PLANNED
        result.stages.append(
            StageResult("plan", "planned", _describe_plan(job, result.audio_muted))
        )
        return result

    import time

    started = time.perf_counter()

    try:
        work_dir = out_dir() / job_id
        work_dir.mkdir(parents=True, exist_ok=True)

        cut_path = work_dir / "cut.mp4"
        cut_info = cut_excerpt(
            str(source_path),
            str(cut_path),
            float(job["start_time"]),
            float(job["end_time"]),
            mute_audio=result.audio_muted,
        )
        result.stages.append(
            StageResult("cut", "ok", cut_info.describe(), str(cut_path))
        )

        policy = load_policy()
        tightest = tightest_platform(policy)
        reframed_path = work_dir / "vertical.mp4"
        reframe_9_16(
            str(cut_path),
            str(reframed_path),
            x_offset_ratio=float(job.get("x_offset_ratio", 0.5) or 0.5),
            width=tightest.width,
            height=tightest.height,
        )
        result.stages.append(
            StageResult(
                "reframe",
                "ok",
                f"{tightest.width}x{tightest.height}",
                str(reframed_path),
            )
        )

        credit_text = generate_credit_text(
            job.get("creator_name", ""), job.get("creator_channel_url")
        )
        final_path = work_dir / f"{job_id}_master_en.mp4"
        burn_credit_overlay(
            str(reframed_path),
            str(final_path),
            credit_text,
            top_margin_pct=tightest.top_safe_pct,
            video_height=tightest.height,
        )
        result.output_path = str(final_path)
        result.stages.append(
            StageResult("credit", "ok", credit_text, str(final_path))
        )

        qa = run_qa(
            final_path,
            expected_width=tightest.width,
            expected_height=tightest.height,
            max_duration_seconds=tightest.max_duration_seconds,
            expect_audio=not result.audio_muted,
            frame_budget_seconds=policy.limits.max_excerpt_seconds,
        )
        result.qa = qa
        result.stages.append(StageResult("qa", "ok" if qa.passed else "failed", qa.summary()))
        result.status = STATUS_SUCCESS if qa.passed else STATUS_QA_FAILED
    except (MediaToolError, FileNotFoundError, ValueError) as exc:
        result.status = STATUS_FAILED
        result.error = str(exc)
        result.stages.append(StageResult("render", "failed", str(exc)))

    result.execution_seconds = time.perf_counter() - started
    append_run_log(result.to_log())
    return result


def _describe_plan(job: dict[str, Any], muted: bool) -> str:
    policy = load_policy()
    tightest = tightest_platform(policy)
    return (
        f"cut {float(job['start_time']):.1f}s-{float(job['end_time']):.1f}s, "
        f"reframe {tightest.width}x{tightest.height}, "
        f"audio={'muted (R10)' if muted else 'kept'}"
    )


def environment_report() -> dict[str, Any]:
    """Facts worth recording before a render run."""
    try:
        policy = load_policy()
        platforms = policy.platform_names()
        tightest = tightest_platform(policy)
        limits = {
            "max_excerpt_seconds": policy.limits.max_excerpt_seconds,
            "max_cutscene_ratio": policy.limits.max_cutscene_ratio,
            "tightest_platform": tightest.name,
            "tightest_max_duration": tightest.max_duration_seconds,
        }
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed silently
        platforms = []
        limits = {"error": str(exc)}

    return {
        "ffmpeg": tool_versions(),
        "platforms": platforms,
        "limits": limits,
    }
