"""Job schema: loading, normalisation, and intake-to-render handoff.

The intake tool and the renderer previously spoke different dialects — intake
emitted ``licensed_music_audible`` and ``category``, the runner expected
``licensed_music_present`` and no category, and there was no way to take a
triaged candidate and render it. This module is that bridge: one normalised job
dict, one loader, and one converter from an intake record.

A job is a plain dict so it round-trips through YAML and JSON without a second
schema definition to keep in sync.
"""

from pathlib import Path
from typing import Any

import yaml

from src.paths import jobs_dir

DEFAULT_PLATFORMS = (
    "youtube_shorts",
    "tiktok",
    "instagram_reels",
    "snapchat_spotlight",
)

# Fields copied straight from an intake result into a job.
PASSTHROUGH_FIELDS = (
    "source_url",
    "creator_name",
    "creator_channel_url",
    "topic_summary",
    "category",
    "sensitivity",
    "start_time",
    "end_time",
    "cutscene_seconds",
    "claim_text",
    "evidence_link",
    "game_version",
    "language_spoken",
    "notes",
)


class JobError(ValueError):
    """Raised when a job file is missing, unreadable, or not a mapping."""


def load_job(path: Path | str) -> dict[str, Any]:
    """Load and normalise a job YAML file."""
    job_path = Path(path)
    if not job_path.is_file():
        raise JobError(f"Job file not found: {job_path}")
    with open(job_path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise JobError(f"Job file {job_path} must contain a YAML mapping.")
    job = normalise_job(raw)
    job.setdefault("_job_path", str(job_path))
    return job


def normalise_job(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce a raw job mapping into the canonical shape."""
    job: dict[str, Any] = dict(raw)

    # Accept both music-field spellings in either direction.
    if "licensed_music_audible" not in job and "licensed_music_present" in job:
        job["licensed_music_audible"] = bool(job["licensed_music_present"])
    job.setdefault("licensed_music_audible", False)

    flags = job.get("content_flags") or []
    if isinstance(flags, str):
        flags = [flags]
    job["content_flags"] = list(flags)

    if job.get("platforms"):
        job["platforms"] = [str(p) for p in job["platforms"]]
    else:
        job.setdefault("platforms", list(DEFAULT_PLATFORMS))

    for field_name in ("start_time", "end_time", "cutscene_seconds"):
        value = job.get(field_name)
        if value is not None and value != "":
            try:
                job[field_name] = float(value)
            except (TypeError, ValueError):
                # Gates report the type problem; do not crash while loading.
                pass

    job.setdefault("id", _default_job_id())
    return job


def _default_job_id() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("job-%Y%m%d-%H%M%S")


def job_from_candidate(
    candidate: dict[str, Any],
    source_file: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Build a render job from a triaged intake candidate.

    Only deterministic metadata is copied. Nothing here marks a candidate as
    cleared: a job that renders still needs documented creator permission and a
    human publishing decision.
    """
    job: dict[str, Any] = {}

    for field_name in PASSTHROUGH_FIELDS:
        if field_name in candidate and candidate[field_name] is not None:
            job[field_name] = candidate[field_name]

    job["id"] = job_id or _default_job_id()
    if source_file:
        job["source_file"] = source_file

    job["licensed_music_audible"] = bool(
        candidate.get("licensed_music_audible")
        or candidate.get("licensed_music_present")
        or False
    )

    flags = candidate.get("content_flags") or []
    if isinstance(flags, str):
        flags = [flags]
    job["content_flags"] = list(flags)

    job["platforms"] = list(
        candidate.get("platforms") or DEFAULT_PLATFORMS
    )

    return normalise_job(job)


def write_job(job: dict[str, Any], path: Path | str) -> Path:
    """Write a job to YAML, stripping internal keys."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in job.items() if not str(k).startswith("_")}
    with open(target, "w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
    return target


def default_job_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.yaml"
