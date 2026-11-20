"""Deterministic gates enforcing the R1-R10 rights and safety rules.

Design notes
------------
* Limits and blocked-content vocabularies come from ``src.policy`` (which reads
  ``config/``). Nothing here hardcodes 40 seconds or 20%.
* Creator opt-out matching comes from ``src.optout``, so intake and the render
  path share one implementation.
* All failures are collected and raised together. An operator who submits a job
  with three problems should see three problems, not discover them one run at a
  time.
* Every gate is a hard eligibility gate. A gate failure is never offset by a
  high editorial score.

The licensed-music rule (R10) is deliberately not a blocking gate. R10 says to
mute before production, not to refuse the job, so the render path forces an
audio mute and QA verifies the result. Blocking here would only teach the
operator to edit the flag.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.optout import find_opt_out_match, load_opt_out_list
from src.policy import (
    BLOCKED_SENSITIVITY,
    SENSITIVITY_LEVELS,
    VALID_CATEGORIES,
    PolicyError,
    load_policy,
)

REQUIRED_JOB_FIELDS = (
    "id",
    "source_url",
    "creator_name",
    "start_time",
    "end_time",
    "sensitivity",
)

# ``licensed_music_present`` was the original field name; the intake tool used
# ``licensed_music_audible``. Accept both, prefer the explicit "audible" name.
MUSIC_FIELDS = ("licensed_music_audible", "licensed_music_present")

CONTENT_FLAGS_FIELD = "content_flags"


class GateValidationError(Exception):
    """Raised when a job fails one or more deterministic policy checks."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = list(failures)
        super().__init__(" ".join(self.failures))


@dataclass
class GateReport:
    """Outcome of a successful gate evaluation."""

    passed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add(self, name: str) -> None:
        self.passed.append(name)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def is_music_audible(job: dict[str, Any]) -> bool:
    """True if the job declares audible licensed or radio music."""
    for name in MUSIC_FIELDS:
        if name in job and job[name] is not None:
            return bool(job[name])
    return False


def _coerce_seconds(value: Any, field_name: str, failures: list[str]) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        failures.append(f"{field_name} must be a number of seconds, got {value!r}.")
        return None


def _check_required_fields(job: dict[str, Any], failures: list[str]) -> None:
    for name in REQUIRED_JOB_FIELDS:
        value = job.get(name)
        if value is None or value == "":
            failures.append(f"Missing required field: {name}.")


def _check_timing(
    job: dict[str, Any], failures: list[str], max_seconds: float
) -> tuple[float, float] | None:
    start = _coerce_seconds(job.get("start_time"), "start_time", failures)
    end = _coerce_seconds(job.get("end_time"), "end_time", failures)
    if start is None or end is None:
        return None
    if start < 0:
        failures.append(f"start_time must not be negative, got {start:.2f}s.")
        return None
    duration = end - start
    if duration <= 0:
        failures.append(
            f"Invalid excerpt window: end_time {end:.2f}s must be after "
            f"start_time {start:.2f}s."
        )
        return None
    if duration > max_seconds:
        failures.append(
            f"Excerpt duration {duration:.1f}s exceeds the {max_seconds:.0f}s "
            "source-excerpt limit (R2)."
        )
        return None
    return start, end


def _check_cutscene_ratio(
    job: dict[str, Any],
    excerpt_seconds: float | None,
    failures: list[str],
    max_ratio: float,
) -> None:
    raw = job.get("cutscene_seconds")
    if raw in (None, "", 0, 0.0):
        return
    cutscene = _coerce_seconds(raw, "cutscene_seconds", failures)
    if cutscene is None:
        return
    if cutscene < 0:
        failures.append(f"cutscene_seconds must not be negative, got {cutscene}.")
        return
    if excerpt_seconds is None or excerpt_seconds <= 0:
        return
    ratio = cutscene / excerpt_seconds
    if ratio > max_ratio:
        failures.append(
            f"Cutscene content is {ratio:.1%} of the excerpt, above the "
            f"{max_ratio:.0%} limit (R9)."
        )


def _check_sensitivity(job: dict[str, Any], failures: list[str]) -> None:
    sensitivity = job.get("sensitivity")
    if sensitivity is None or sensitivity == "":
        return  # Already reported by the required-fields gate.
    if sensitivity == BLOCKED_SENSITIVITY:
        failures.append(
            f"Sensitivity {BLOCKED_SENSITIVITY!r} content is not published in the "
            "current phase."
        )
        return
    if sensitivity not in SENSITIVITY_LEVELS:
        failures.append(
            f"Unknown sensitivity {sensitivity!r}. "
            f"Expected one of: {', '.join(SENSITIVITY_LEVELS)}."
        )


def _check_category(job: dict[str, Any], failures: list[str]) -> None:
    category = job.get("category")
    if category is None or category == "":
        return  # Optional on render jobs; required on intake candidates.
    if category not in VALID_CATEGORIES:
        failures.append(
            f"Unknown category {category!r}. "
            f"Expected one of: {', '.join(VALID_CATEGORIES)}."
        )


def _check_content_flags(
    job: dict[str, Any], failures: list[str], hard_blocked: tuple[str, ...]
) -> None:
    flags = job.get(CONTENT_FLAGS_FIELD) or []
    if isinstance(flags, str):
        flags = [flags]
    if not isinstance(flags, list):
        failures.append(
            f"{CONTENT_FLAGS_FIELD} must be a list of content traits, "
            f"got {type(flags).__name__}."
        )
        return
    for flag in flags:
        if flag in hard_blocked:
            failures.append(
                f"Content trait {flag!r} is hard-blocked "
                "(R9, config/blocked_content.yaml)."
            )


def _check_claim_evidence(job: dict[str, Any], failures: list[str]) -> None:
    claim = str(job.get("claim_text") or "").strip()
    evidence = str(job.get("evidence_link") or "").strip()
    if claim and not evidence:
        failures.append(
            "A factual claim is present without an evidence_link (R8). "
            "Attach primary evidence or remove the claim."
        )


def _check_creator_opt_out(job: dict[str, Any], failures: list[str]) -> None:
    entries = load_opt_out_list()
    match = find_opt_out_match(
        job.get("creator_name"),
        job.get("creator_channel_url"),
        entries,
    )
    if match:
        failures.append(match.describe())


def _check_platforms(
    job: dict[str, Any],
    report: GateReport,
    failures: list[str],
    known: list[str],
) -> None:
    platforms = job.get("platforms")
    if platforms is None:
        report.warn(
            "No target platforms declared; QA will use the strictest platform limit."
        )
        return
    if not isinstance(platforms, list) or not platforms:
        failures.append("platforms must be a non-empty list when provided.")
        return
    unknown = [p for p in platforms if p not in known]
    if unknown:
        failures.append(
            f"Unknown target platform(s): {', '.join(map(str, unknown))}. "
            f"Known: {', '.join(known)}."
        )


def collect_gate_failures(job: dict[str, Any]) -> tuple[list[str], GateReport]:
    """Evaluate every gate and return all failures plus a report."""
    report = GateReport()
    failures: list[str] = []

    try:
        policy = load_policy()
    except PolicyError as exc:
        raise GateValidationError([f"Policy configuration unusable: {exc}"]) from exc

    _check_required_fields(job, failures)
    _check_sensitivity(job, failures)
    _check_category(job, failures)
    _check_content_flags(job, failures, policy.hard_blocked_traits)
    _check_claim_evidence(job, failures)
    _check_creator_opt_out(job, failures)
    _check_platforms(job, report, failures, policy.platform_names())

    timing = _check_timing(job, failures, policy.limits.max_excerpt_seconds)
    excerpt_seconds = (timing[1] - timing[0]) if timing else None
    _check_cutscene_ratio(
        job, excerpt_seconds, failures, policy.limits.max_cutscene_ratio
    )

    if is_music_audible(job):
        report.warn(
            "Licensed or radio music is flagged as audible. The render path will "
            "mute the source audio (R10) and QA will verify no audio stream survives."
        )

    source_file = job.get("source_file")
    if not source_file:
        report.warn(
            "No source_file declared. Gates pass, but rendering stops at the "
            "source-file stage."
        )
    elif not Path(str(source_file)).expanduser().is_file():
        report.warn(
            f"source_file {source_file!r} is not present on this machine yet."
        )

    if not failures:
        report.add("required_fields_present")
        report.add("sensitivity_approved")
        report.add("category_valid")
        report.add("content_traits_allowed")
        report.add("claim_evidence_aligned")
        report.add("creator_opt_out_clear")
        report.add("platforms_known")
        report.add("duration_within_limit")
        report.add("cutscene_ratio_valid")

    return failures, report


def validate_job_gates(job: dict[str, Any]) -> GateReport:
    """Validate a job dict against every deterministic gate.

    Returns a :class:`GateReport` on success and raises
    :class:`GateValidationError` listing every failure otherwise.
    """
    if not isinstance(job, dict):
        raise GateValidationError(
            [f"Job must be a mapping, got {type(job).__name__}."]
        )
    failures, report = collect_gate_failures(job)
    if failures:
        raise GateValidationError(failures)
    return report
