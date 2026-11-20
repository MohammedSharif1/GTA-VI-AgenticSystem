#!/usr/bin/env python3
"""The Find Feed — Phase 1 intake and triage.

A local, deterministic intake tool for GTA VI clip candidates. It accepts
manually entered metadata, validates it against the reviewed policy in
``config/``, checks for likely duplicates from the past seven days, flags risks,
and writes structured logs.

It is not an agent. It does not download or process media, contact creators or
platforms, publish anything, or grant permission or rights clearance.
``publish_clearance`` is always ``False``.

Usage:
    python src/find_feed.py --example
    python src/find_feed.py --input candidate.json
    python src/find_feed.py --interactive
    python src/find_feed.py --input candidate.json --emit-job jobs/new.yaml

Requires Python 3.11+ and PyYAML. No paid services or API keys.
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.job import job_from_candidate, write_job  # noqa: E402
from src.optout import find_opt_out_match, load_opt_out_list  # noqa: E402
from src.paths import candidates_dir, runs_log_path  # noqa: E402
from src.policy import (  # noqa: E402
    BLOCKED_SENSITIVITY,
    SENSITIVITY_LEVELS,
    VALID_CATEGORIES,
    PolicyError,
    load_policy,
)

DUPLICATE_WINDOW_DAYS = 7
DUPLICATE_OVERLAP_THRESHOLD = 0.5

REQUIRED_FIELDS = (
    "source_url",
    "creator_name",
    "topic_summary",
    "category",
    "sensitivity",
)

STOP_WORDS = frozenset(
    {
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "is", "are",
        "and", "or", "it", "this", "that", "with", "from", "gta", "vi",
        "you", "can", "how", "new", "was", "but", "not", "as", "by",
    }
)

PERMISSION_REMINDER = (
    "REMINDER: documented creator permission is required before public posting. "
    "This tool does not check or grant permission."
)

SAMPLE_CANDIDATE = {
    "source_url": "https://youtube.com/watch?v=EXAMPLE",
    "creator_name": "ViceCityExplorer",
    "creator_channel_url": "https://youtube.com/@ViceCityExplorer",
    "topic_summary": "Hidden underwater cave off Vice Beach leads to a submarine bunker",
    "category": "new_discovery",
    "sensitivity": "Green",
    "start_time": 14.5,
    "end_time": 42.0,
    "cutscene_seconds": 0.0,
    "claim_text": "Submarine bunker accessible through Vice Beach underwater cave",
    "evidence_link": "https://reddit.com/r/GTA6/comments/EXAMPLE",
    "licensed_music_audible": False,
    "content_flags": [],
    "game_version": "1.00",
    "language_spoken": "en",
    "notes": "Creator speaks English. Good visual quality. No radio music.",
}


class TriageInputError(ValueError):
    """Raised when a candidate file cannot be read as a JSON object."""


def new_candidate_id(now: datetime | None = None) -> str:
    """Sortable, collision-resistant identifier.

    The previous implementation used a bare second-resolution timestamp, so two
    candidates submitted in the same second overwrote each other's record.
    """
    moment = now or datetime.now(timezone.utc)
    return f"{moment.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def load_recent_candidates(window_days: int = DUPLICATE_WINDOW_DAYS) -> list[dict[str, Any]]:
    """Load candidate records written in the last ``window_days`` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    directory = candidates_dir()
    if not directory.exists():
        return []

    recent: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                record = json.load(handle)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(record, dict):
            continue
        moment = _parse_timestamp(record.get("timestamp"))
        if moment is not None and moment >= cutoff:
            recent.append(record)
    return recent


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # Mixed naive/aware timestamps would raise on comparison, not on parsing.
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _keywords(text: str) -> set[str]:
    return {
        word.strip(".,!?:;'\"()[]").lower()
        for word in (text or "").split()
        if word.strip(".,!?:;'\"()[]")
    } - STOP_WORDS


def find_likely_duplicates(
    topic: str, recent: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Advisory keyword-overlap check against recent topics.

    The operator still makes the duplicate decision; this only surfaces
    candidates worth re-reading before spending time on a draft.
    """
    words = _keywords(topic)
    if not words:
        return []

    matches: list[dict[str, str]] = []
    for record in recent:
        existing_summary = saved_topic_summary(record)
        existing_words = _keywords(existing_summary)
        if not existing_words:
            continue
        overlap = words & existing_words
        ratio = len(overlap) / len(words)
        if ratio < DUPLICATE_OVERLAP_THRESHOLD:
            continue
        matches.append(
            {
                "candidate_id": str(record.get("candidate_id") or "?"),
                "topic_summary": existing_summary,
                "overlap": ", ".join(sorted(overlap)),
            }
        )
    return matches


def triage_candidate(
    candidate: dict[str, Any], recent: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Validate a candidate and return the triage record."""
    try:
        policy = load_policy()
    except PolicyError as exc:
        raise PolicyError(f"Policy configuration unusable: {exc}") from exc

    now = datetime.now(timezone.utc)
    flags: list[str] = []
    missing: list[str] = []
    gates: dict[str, bool | None] = {}
    status = "accepted"

    def fail(reason: str, gate: str, *, blocking: bool = False) -> None:
        nonlocal status
        flags.append(reason)
        gates[gate] = False
        status = "blocked" if blocking else ("needs_review" if status == "accepted" else status)

    if not isinstance(candidate, dict):
        raise TriageInputError(f"Candidate must be a JSON object, got {type(candidate).__name__}.")

    # Gate 1: required fields
    for field_name in REQUIRED_FIELDS:
        value = candidate.get(field_name)
        if value is None or value == "":
            missing.append(field_name)
    gates["required_fields"] = not missing
    if missing:
        flags.append(f"Missing required fields: {', '.join(missing)}")
        status = "needs_review"

    # Gate 2: category
    category = candidate.get("category")
    if category and category not in VALID_CATEGORIES:
        fail(
            f"Unknown category {category!r}. Valid: {', '.join(VALID_CATEGORIES)}.",
            "valid_category",
        )
    else:
        gates["valid_category"] = bool(category)

    # Gate 3: hard-blocked content traits (R9) — previously defined but unchecked
    raw_flags = candidate.get("content_flags") or []
    if isinstance(raw_flags, str):
        raw_flags = [raw_flags]
    if not isinstance(raw_flags, list):
        fail("content_flags must be a list of traits.", "content_traits_allowed")
    else:
        disallowed = [f for f in raw_flags if f in policy.hard_blocked_traits]
        unknown = [f for f in raw_flags if f not in policy.hard_blocked_traits]
        gates["content_traits_allowed"] = not disallowed
        for trait in disallowed:
            fail(
                f"Content trait {trait!r} is hard-blocked (R9). "
                "This material is not published in the current phase.",
                "content_traits_allowed",
                blocking=True,
            )
        for trait in unknown:
            flags.append(
                f"Unrecognised content trait {trait!r}. Add it to "
                "config/blocked_content.yaml and src/policy.py before relying on it."
            )

    # Gate 4: sensitivity
    sensitivity = candidate.get("sensitivity")
    if sensitivity == BLOCKED_SENSITIVITY:
        fail(
            f"Sensitivity {BLOCKED_SENSITIVITY!r} is hard-blocked in the current phase.",
            "sensitivity_ok",
            blocking=True,
        )
    elif sensitivity and sensitivity not in SENSITIVITY_LEVELS:
        fail(
            f"Unknown sensitivity {sensitivity!r}. Valid: {', '.join(SENSITIVITY_LEVELS)}.",
            "sensitivity_ok",
        )
    else:
        gates["sensitivity_ok"] = sensitivity in SENSITIVITY_LEVELS

    start, end = candidate.get("start_time"), candidate.get("end_time")
    duration: float | None = None
    if start is not None and end is not None:
        try:
            duration = float(end) - float(start)
        except (TypeError, ValueError):
            fail("start_time and end_time must be numeric seconds.", "duration_ok")
        else:
            if duration <= 0:
                fail(f"Invalid window: end_time must be after start_time ({duration:.1f}s).", "duration_ok", blocking=True)
            elif duration > policy.limits.max_excerpt_seconds:
                fail(
                    f"Excerpt {duration:.1f}s exceeds the "
                    f"{policy.limits.max_excerpt_seconds:.0f}s source limit (R2).",
                    "duration_ok",
                    blocking=True,
                )
            else:
                gates["duration_ok"] = True
    else:
        gates["duration_ok"] = None

    # Gate 5: cutscene ratio
    cutscene_raw = candidate.get("cutscene_seconds") or 0
    if duration and duration > 0:
        try:
            ratio = float(cutscene_raw) / duration
        except (TypeError, ValueError):
            fail("cutscene_seconds must be numeric.", "cutscene_ratio_ok")
        else:
            if ratio > policy.limits.max_cutscene_ratio:
                fail(
                    f"Cutscene content is {ratio:.0%} of the excerpt, above the "
                    f"{policy.limits.max_cutscene_ratio:.0%} limit (R9).",
                    "cutscene_ratio_ok",
                    blocking=True,
                )
            else:
                gates["cutscene_ratio_ok"] = True
    else:
        gates["cutscene_ratio_ok"] = True

    # Gate 6: claim needs evidence
    claim = str(candidate.get("claim_text") or "").strip()
    evidence = str(candidate.get("evidence_link") or "").strip()
    if claim and not evidence:
        fail("A factual claim has no evidence_link (R8).", "claim_evidence_ok")
    else:
        gates["claim_evidence_ok"] = True

    # Gate 7: licensed music is a production instruction, not a blocker
    music_audible = bool(
        candidate.get("licensed_music_audible")
        or candidate.get("licensed_music_present")
        or False
    )
    gates["music_ok"] = not music_audible
    if music_audible:
        flags.append(
            "Licensed or radio music is audible. The renderer will mute the "
            "source audio (R10); QA verifies no audio stream survives."
        )

    # Gate 8: creator opt-out
    match = find_opt_out_match(
        candidate.get("creator_name"),
        candidate.get("creator_channel_url"),
        load_opt_out_list(),
    )
    gates["not_blocked_creator"] = match is None
    if match:
        fail(match.describe(), "not_blocked_creator", blocking=True)

    # Advisory: duplicates
    pool = recent if recent is not None else load_recent_candidates()
    duplicates = find_likely_duplicates(str(candidate.get("topic_summary") or ""), pool)
    if duplicates:
        flags.append(
            f"Possible duplicate of {len(duplicates)} recent topic(s); check the "
            "seven-day coverage list before drafting."
        )

    flags.append(PERMISSION_REMINDER)

    return {
        "candidate_id": new_candidate_id(now),
        "timestamp": now.isoformat(),
        "status": status,
        "input": candidate,
        "flags": flags,
        "missing_fields": missing,
        "possible_duplicates": duplicates,
        "gate_results": gates,
        "music_audible": music_audible,
        "publish_clearance": False,
        "permission_verified": False,
    }


def saved_topic_summary(record: dict[str, Any]) -> str:
    """Topic text from a saved record.

    Saved records nest the candidate under ``input``, so the duplicate check
    must look there; reading only the top level compared every new topic against
    an empty string and never found a duplicate.
    """
    nested = record.get("input")
    if isinstance(nested, dict):
        return str(nested.get("topic_summary") or "")
    return str(record.get("topic_summary") or "")


def save_candidate_record(record: dict[str, Any]) -> Path:
    """Persist the full triage record under ``logs/candidates/``."""
    directory = candidates_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['candidate_id']}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    return path


def append_run_log(record: dict[str, Any]) -> Path:
    """Append a one-line summary to ``logs/runs.jsonl``."""
    path = runs_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "candidate_id": record["candidate_id"],
        "timestamp": record["timestamp"],
        "status": record["status"],
        "flags_count": len(record["flags"]),
        "missing_fields_count": len(record["missing_fields"]),
        "duplicates_count": len(record["possible_duplicates"]),
        "music_audible": record.get("music_audible", False),
        "publish_clearance": False,
        "permission_verified": False,
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return path


def print_triage(record: dict[str, Any]) -> None:
    """Print a readable triage summary."""
    status = str(record["status"]).upper()
    icon = {"ACCEPTED": "OK", "BLOCKED": "XX", "NEEDS_REVIEW": "??"}.get(status, "--")
    source = record["input"]

    print()
    print("=" * 72)
    print(f"  [{icon}] Candidate {record['candidate_id']} — {status}")
    print("=" * 72)
    print(f"  Topic:       {source.get('topic_summary', '(none)')}")
    print(f"  Creator:     {source.get('creator_name', '(unknown)')}")
    print(f"  Category:    {source.get('category', '-')}")
    print(f"  Sensitivity: {source.get('sensitivity', '-')}")
    print()
    print("  Gates:")
    for gate, passed in record["gate_results"].items():
        mark = "pass" if passed is True else ("FAIL" if passed is False else "n/a ")
        print(f"    [{mark}] {gate}")
    print()

    if record["flags"]:
        print(f"  Flags ({len(record['flags'])}):")
        for flag in record["flags"]:
            print(f"    - {flag}")
        print()

    if record["missing_fields"]:
        print(f"  Missing fields: {', '.join(record['missing_fields'])}")
        print()

    if record["possible_duplicates"]:
        print(f"  Possible duplicates in the last {DUPLICATE_WINDOW_DAYS} days:")
        for duplicate in record["possible_duplicates"]:
            print(f"    - [{duplicate['candidate_id']}] {duplicate['topic_summary']}")
        print()

    print("  Publish clearance: NO (always requires the operator)")
    print("  Permission verified: NO (this tool never verifies permission)")
    print("=" * 72)


def interactive_input() -> dict[str, Any]:
    """Collect candidate fields from the terminal."""
    print("\n--- The Find Feed: new candidate ---\n")
    candidate: dict[str, Any] = {}

    candidate["source_url"] = input("Source URL: ").strip()
    candidate["creator_name"] = input("Creator name: ").strip()
    candidate["creator_channel_url"] = (
        input("Creator channel URL (optional): ").strip() or None
    )
    candidate["topic_summary"] = input("Topic summary (one line): ").strip()

    print(f"Categories: {', '.join(VALID_CATEGORIES)}")
    candidate["category"] = input("Category: ").strip()

    print(f"Sensitivity levels: {', '.join(SENSITIVITY_LEVELS)}")
    candidate["sensitivity"] = input("Sensitivity: ").strip()

    start = _prompt_float("Start time in seconds (optional): ")
    end = _prompt_float("End time in seconds (optional): ")
    if start is not None:
        candidate["start_time"] = start
    if end is not None:
        candidate["end_time"] = end

    cutscene = _prompt_float("Cutscene seconds (default 0): ")
    candidate["cutscene_seconds"] = cutscene if cutscene is not None else 0.0

    candidate["claim_text"] = input("Factual claim (optional): ").strip() or None
    if candidate["claim_text"]:
        candidate["evidence_link"] = input("Evidence link for the claim: ").strip() or None

    candidate["licensed_music_audible"] = (
        input("Licensed/radio music audible? (y/n, default n): ").strip().lower() == "y"
    )

    flags = input("Content traits, comma-separated (optional): ").strip()
    candidate["content_flags"] = [f.strip() for f in flags.split(",") if f.strip()]

    candidate["game_version"] = input("Game version (e.g. 1.00): ").strip() or None
    candidate["language_spoken"] = input("Language spoken (e.g. en, ar): ").strip() or None
    candidate["notes"] = input("Notes (optional): ").strip() or None

    return {k: v for k, v in candidate.items() if v is not None}


def _prompt_float(prompt: str) -> float | None:
    raw = input(prompt).strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        print(f"  (ignoring non-numeric value {raw!r})")
        return None


def _read_candidate_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TriageInputError(f"Candidate file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise TriageInputError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise TriageInputError(
            f"{path} must contain a JSON object, got {type(payload).__name__}."
        )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="The Find Feed — Phase 1 intake and triage",
        epilog=(
            "This tool validates candidates. It does not publish, download, "
            "contact creators, or grant clearance."
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--example", action="store_true", help="Use the built-in sample candidate")
    group.add_argument("--input", metavar="FILE", help="Path to a candidate JSON file")
    group.add_argument("--interactive", action="store_true", help="Enter fields interactively")
    parser.add_argument(
        "--emit-job",
        metavar="PATH",
        help="Also write a render job YAML for this candidate",
    )
    parser.add_argument(
        "--source-file",
        metavar="PATH",
        help="Local media path to record in the emitted job",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Do not write logs (useful for a dry test drive)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.example:
            candidate = dict(SAMPLE_CANDIDATE)
            print("[Using the built-in sample candidate]")
        elif args.input:
            candidate = _read_candidate_file(Path(args.input))
        else:
            candidate = interactive_input()

        record = triage_candidate(candidate)
    except (TriageInputError, PolicyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print_triage(record)

    if not args.no_log:
        record_path = save_candidate_record(record)
        run_log = append_run_log(record)
        print(f"  Candidate record: {record_path}")
        print(f"  Run log:          {run_log}")

    if args.emit_job:
        job = job_from_candidate(
            record["input"],
            source_file=args.source_file,
            job_id=record["candidate_id"],
        )
        job["candidate_status"] = record["status"]
        job_path = write_job(job, Path(args.emit_job))
        print(f"  Job written:      {job_path}")
        print("  The job still requires documented permission and a QA pass.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
