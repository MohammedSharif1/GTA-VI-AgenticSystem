"""Deterministic validation gates enforcing R1-R10 rules."""

from pathlib import Path
from typing import Dict, Any, List
import csv


class GateValidationError(Exception):
    """Raised when a job fails deterministic policy or safety checks."""
    pass


def load_do_not_post(csv_path: str = "config/do_not_post.csv") -> List[Dict[str, str]]:
    """Loads creator opt-out list."""
    path = Path(csv_path)
    if not path.exists():
        return []
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def check_creator_opt_out(creator_name: str, channel_url: str, do_not_post_list: List[Dict[str, str]]) -> None:
    """Verifies that creator or channel is not on the do-not-post list."""
    norm_name = creator_name.strip().lower()
    norm_url = channel_url.strip().lower()
    for entry in do_not_post_list:
        if entry.get("creator_name", "").strip().lower() == norm_name:
            raise GateValidationError(f"Creator '{creator_name}' is on the do-not-post list.")
        for col in ["youtube_url", "tiktok_handle", "instagram_handle", "twitter_handle"]:
            val = entry.get(col, "").strip().lower()
            if val and (val in norm_url or norm_url in val):
                raise GateValidationError(f"Creator channel '{channel_url}' matches opt-out record: {entry}.")


def validate_job_gates(job: Dict[str, Any], do_not_post_path: str = "config/do_not_post.csv") -> List[str]:
    """
    Validates a job specification against all deterministic gates.
    Returns list of passed checks or raises GateValidationError.
    """
    passed = []

    # 1. Required fields
    required = ["id", "source_url", "creator_name", "start_time", "end_time", "sensitivity"]
    for field in required:
        if field not in job or job[field] is None:
            raise GateValidationError(f"Missing required field: {field}")
    passed.append("required_fields_present")

    # 2. Check do-not-post list
    opt_out_list = load_do_not_post(do_not_post_path)
    check_creator_opt_out(job["creator_name"], job.get("creator_channel_url", ""), opt_out_list)
    passed.append("opt_out_check_passed")

    # 3. Excerpt duration rule (R2: max 40s)
    duration = float(job["end_time"]) - float(job["start_time"])
    if duration <= 0:
        raise GateValidationError(f"Invalid duration: {duration}s")
    if duration > 40.0:
        raise GateValidationError(f"Excerpt duration {duration:.1f}s exceeds max 40.0s (Rule R2).")
    passed.append("duration_within_limit")

    # 4. Cutscene ratio (Max 20% runtime)
    cutscene_sec = float(job.get("cutscene_seconds", 0.0))
    if cutscene_sec > 0:
        ratio = (cutscene_sec / duration) * 100
        if ratio > 20.0:
            raise GateValidationError(f"Cutscene ratio {ratio:.1f}% exceeds 20.0% max limit.")
    passed.append("cutscene_ratio_valid")

    # 5. Sensitivity check
    sensitivity = job.get("sensitivity", "Green")
    if sensitivity == "Red":
        raise GateValidationError("Job marked as 'Red' sensitivity. Hard-blocked in v1.")
    passed.append("sensitivity_approved")

    # 6. Claim and Evidence check (R8)
    claim_text = job.get("claim_text")
    evidence_link = job.get("evidence_link")
    if claim_text and not evidence_link:
        raise GateValidationError("Claim provided without verified evidence_link (Rule R8).")
    passed.append("claim_evidence_aligned")

    # 7. Licensed music check (R10)
    if job.get("licensed_music_present", False):
        raise GateValidationError("Licensed music flagged as present. Mute or trim before processing (Rule R10).")
    passed.append("music_cleared")

    return passed
