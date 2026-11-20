#!/usr/bin/env python3
"""
The Find Feed — Phase 1 Intake and Triage Tool

A local, deterministic intake tool for GTA VI clip candidates. It accepts
manually entered metadata, validates required fields, checks for duplicate
topics from the previous 7 days, flags risks, and writes structured candidate
and run logs.

This is NOT an autonomous agent. It does not:
- Download or process source media
- Contact creators or platforms
- Publish or authorize publication
- Grant permission or rights clearance

publish_clearance is always False. The operator makes all posting decisions.

Usage:
    python src/find_feed.py --example          # Run with a built-in sample
    python src/find_feed.py --input candidate.json   # Process a candidate file
    python src/find_feed.py --interactive       # Enter candidate interactively

Dependencies: Python 3.11+ (standard library only, no paid services)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_EXCERPT_SECONDS = 40
MAX_CUTSCENE_RATIO = 0.20
DUPLICATE_WINDOW_DAYS = 7
SENSITIVITY_BLOCKED = "Red"

VALID_CATEGORIES = [
    "new_discovery",
    "fast_guide",
    "patch_change",
    "funny_moment",
    "other_useful",
]

VALID_SENSITIVITY = ["Green", "Yellow", "Red"]

HARD_BLOCKED_CATEGORIES = [
    "story_endings_and_major_plot_reveals",
    "edited_compilations_of_cutscenes_or_story_dialogue",
    "isolated_cinematics_without_gameplay",
    "cheats_mods_exploits",
    "in_game_tv_or_comedy_shows_standalone",
    "leaks_unreleased_builds",
]

REQUIRED_FIELDS = [
    "source_url",
    "creator_name",
    "topic_summary",
    "category",
    "sensitivity",
]

CANDIDATE_LOG_DIR = Path("logs/candidates")
RUN_LOG_PATH = Path("logs/runs.jsonl")
DO_NOT_POST_PATH = Path("config/do_not_post.csv")

# ---------------------------------------------------------------------------
# Sample candidate (used by --example)
# ---------------------------------------------------------------------------

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
    "game_version": "1.00",
    "language_spoken": "en",
    "notes": "Creator speaks English. Good visual quality. No radio music.",
}

# ---------------------------------------------------------------------------
# Do-not-post list loader
# ---------------------------------------------------------------------------


def load_do_not_post() -> list[dict[str, str]]:
    """Load creator opt-out list from CSV. Returns empty list if not found."""
    if not DO_NOT_POST_PATH.exists():
        return []
    import csv

    with open(DO_NOT_POST_PATH, mode="r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_blocked_creator(
    creator_name: str, channel_url: str, opt_out_list: list[dict[str, str]]
) -> str | None:
    """Returns reason string if creator is blocked, None otherwise."""
    cn = creator_name.strip().lower()
    cu = channel_url.strip().lower() if channel_url else ""
    for entry in opt_out_list:
        if entry.get("creator_name", "").strip().lower() == cn:
            return f"Creator '{creator_name}' is on the do-not-post list (reason: {entry.get('reason', 'unspecified')})."
        for col in [
            "youtube_url",
            "tiktok_handle",
            "instagram_handle",
            "twitter_handle",
        ]:
            val = entry.get(col, "").strip().lower()
            if val and cu and (val in cu or cu in val):
                return f"Channel URL matches opt-out record for '{entry.get('creator_name', '?')}'."
    return None


# ---------------------------------------------------------------------------
# Recent topic loader (7-day duplicate check)
# ---------------------------------------------------------------------------


def load_recent_topics() -> list[dict[str, Any]]:
    """Load candidate records from the last 7 days for duplicate checking."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=DUPLICATE_WINDOW_DAYS)
    recent = []
    if not CANDIDATE_LOG_DIR.exists():
        return recent
    for f in sorted(CANDIDATE_LOG_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
            ts = rec.get("timestamp")
            if ts:
                rec_time = datetime.fromisoformat(ts)
                if rec_time >= cutoff:
                    recent.append(rec)
        except (json.JSONDecodeError, ValueError, KeyError):
            continue
    return recent


def find_possible_duplicates(topic: str, recent: list[dict[str, Any]]) -> list[str]:
    """
    Simple keyword overlap duplicate check. Returns list of similar topic
    summaries from the last 7 days. This is a basic heuristic — the operator
    makes the final duplicate judgment.
    """
    if not topic:
        return []
    topic_words = set(topic.lower().split())
    # Remove very common words
    stop_words = {
        "the", "a", "an", "in", "on", "at", "to", "for", "of", "is",
        "and", "or", "it", "this", "that", "with", "from", "gta", "vi",
        "you", "can", "how", "new",
    }
    topic_words -= stop_words
    if not topic_words:
        return []

    matches = []
    for rec in recent:
        existing = rec.get("topic_summary", "")
        existing_words = set(existing.lower().split()) - stop_words
        if not existing_words:
            continue
        overlap = topic_words & existing_words
        ratio = len(overlap) / max(len(topic_words), 1)
        if ratio >= 0.5:
            matches.append(
                f"[{rec.get('candidate_id', '?')}] {existing}"
            )
    return matches


# ---------------------------------------------------------------------------
# Validation and triage
# ---------------------------------------------------------------------------


def validate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """
    Validates a candidate against deterministic rules.
    Returns a result dict with:
      - candidate_id
      - status: "accepted" | "blocked" | "needs_review"
      - flags: list of warnings/issues
      - missing_fields: list of missing required fields
      - possible_duplicates: list of similar recent topics
      - publish_clearance: always False
      - gate_results: dict of each gate check
    """
    now = datetime.now(timezone.utc)
    candidate_id = f"{now.strftime('%Y%m%d-%H%M%S')}"

    result: dict[str, Any] = {
        "candidate_id": candidate_id,
        "timestamp": now.isoformat(),
        "input": candidate,
        "status": "accepted",
        "flags": [],
        "missing_fields": [],
        "possible_duplicates": [],
        "publish_clearance": False,  # Always false. Operator decides.
        "gate_results": {},
    }

    # --- Gate 1: Required fields ---
    missing = []
    for field in REQUIRED_FIELDS:
        if field not in candidate or not candidate[field]:
            missing.append(field)
    result["missing_fields"] = missing
    if missing:
        result["flags"].append(f"Missing required fields: {', '.join(missing)}")
        result["status"] = "needs_review"
    result["gate_results"]["required_fields"] = len(missing) == 0

    # --- Gate 2: Category validation ---
    cat = candidate.get("category", "")
    if cat and cat not in VALID_CATEGORIES:
        result["flags"].append(
            f"Unknown category '{cat}'. Valid: {', '.join(VALID_CATEGORIES)}"
        )
        result["status"] = "needs_review"
        result["gate_results"]["valid_category"] = False
    else:
        result["gate_results"]["valid_category"] = bool(cat)

    # --- Gate 3: Sensitivity check ---
    sensitivity = candidate.get("sensitivity", "")
    if sensitivity == SENSITIVITY_BLOCKED:
        result["flags"].append(
            "Sensitivity is 'Red' — hard-blocked in current phase."
        )
        result["status"] = "blocked"
    elif sensitivity and sensitivity not in VALID_SENSITIVITY:
        result["flags"].append(f"Unknown sensitivity '{sensitivity}'.")
        result["status"] = "needs_review"
    result["gate_results"]["sensitivity_ok"] = sensitivity in (
        "Green",
        "Yellow",
    )

    # --- Gate 4: Excerpt duration ---
    start = candidate.get("start_time")
    end = candidate.get("end_time")
    if start is not None and end is not None:
        try:
            duration = float(end) - float(start)
            if duration <= 0:
                result["flags"].append(f"Invalid duration: {duration:.1f}s")
                result["status"] = "blocked"
                result["gate_results"]["duration_ok"] = False
            elif duration > MAX_EXCERPT_SECONDS:
                result["flags"].append(
                    f"Excerpt {duration:.1f}s exceeds {MAX_EXCERPT_SECONDS}s limit."
                )
                result["status"] = "blocked"
                result["gate_results"]["duration_ok"] = False
            else:
                result["gate_results"]["duration_ok"] = True
        except (TypeError, ValueError):
            result["flags"].append("start_time or end_time is not numeric.")
            result["gate_results"]["duration_ok"] = False
    else:
        result["gate_results"]["duration_ok"] = None  # Not provided yet

    # --- Gate 5: Cutscene ratio ---
    cutscene_sec = candidate.get("cutscene_seconds", 0)
    if start is not None and end is not None and cutscene_sec:
        try:
            duration = float(end) - float(start)
            if duration > 0:
                ratio = float(cutscene_sec) / duration
                if ratio > MAX_CUTSCENE_RATIO:
                    result["flags"].append(
                        f"Cutscene ratio {ratio:.0%} exceeds {MAX_CUTSCENE_RATIO:.0%} limit."
                    )
                    result["status"] = "blocked"
                    result["gate_results"]["cutscene_ratio_ok"] = False
                else:
                    result["gate_results"]["cutscene_ratio_ok"] = True
        except (TypeError, ValueError):
            pass
    else:
        result["gate_results"]["cutscene_ratio_ok"] = True

    # --- Gate 6: Claim-evidence alignment ---
    claim = candidate.get("claim_text")
    evidence = candidate.get("evidence_link")
    if claim and not evidence:
        result["flags"].append("Claim provided without evidence_link.")
        result["status"] = "needs_review"
        result["gate_results"]["claim_evidence_ok"] = False
    else:
        result["gate_results"]["claim_evidence_ok"] = True

    # --- Gate 7: Licensed music ---
    if candidate.get("licensed_music_audible", False):
        result["flags"].append(
            "Licensed/radio music audible — must mute before production."
        )
        if result["status"] == "accepted":
            result["status"] = "needs_review"
        result["gate_results"]["music_ok"] = False
    else:
        result["gate_results"]["music_ok"] = True

    # --- Gate 8: Do-not-post list ---
    creator = candidate.get("creator_name", "")
    channel = candidate.get("creator_channel_url", "")
    opt_out_list = load_do_not_post()
    block_reason = is_blocked_creator(creator, channel, opt_out_list)
    if block_reason:
        result["flags"].append(block_reason)
        result["status"] = "blocked"
        result["gate_results"]["not_blocked_creator"] = False
    else:
        result["gate_results"]["not_blocked_creator"] = True

    # --- Duplicate check (advisory, not a gate) ---
    topic = candidate.get("topic_summary", "")
    recent = load_recent_topics()
    dupes = find_possible_duplicates(topic, recent)
    result["possible_duplicates"] = dupes
    if dupes:
        result["flags"].append(
            f"Possible duplicate of {len(dupes)} recent topic(s) — review before proceeding."
        )

    # --- Permission status (always a flag, never cleared by this tool) ---
    result["flags"].append(
        "REMINDER: Permission must be secured before public posting. "
        "This tool does not check or grant permission."
    )

    return result


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def save_candidate_log(result: dict[str, Any]) -> Path:
    """Saves candidate record to logs/candidates/<id>.json."""
    CANDIDATE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = CANDIDATE_LOG_DIR / f"{result['candidate_id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path


def append_run_log(result: dict[str, Any]) -> None:
    """Appends a summary line to logs/runs.jsonl."""
    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "candidate_id": result["candidate_id"],
        "timestamp": result["timestamp"],
        "status": result["status"],
        "flags_count": len(result["flags"]),
        "missing_fields_count": len(result["missing_fields"]),
        "duplicates_count": len(result["possible_duplicates"]),
        "publish_clearance": result["publish_clearance"],
    }
    with open(RUN_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


def print_result(result: dict[str, Any]) -> None:
    """Prints a readable summary of the triage result."""
    status = result["status"].upper()
    cid = result["candidate_id"]
    topic = result["input"].get("topic_summary", "(no topic)")
    creator = result["input"].get("creator_name", "(unknown)")

    status_icon = {"ACCEPTED": "✓", "BLOCKED": "✗", "NEEDS_REVIEW": "?"}
    icon = status_icon.get(status, "·")

    print(f"\n{'='*70}")
    print(f"  [{icon}] Candidate {cid}  —  {status}")
    print(f"{'='*70}")
    print(f"  Topic:    {topic}")
    print(f"  Creator:  {creator}")
    print(f"  Category: {result['input'].get('category', '—')}")
    print(f"  Sensitivity: {result['input'].get('sensitivity', '—')}")
    print()

    # Gate results
    print("  Gate checks:")
    for gate, passed in result["gate_results"].items():
        if passed is True:
            print(f"    [✓] {gate}")
        elif passed is False:
            print(f"    [✗] {gate}")
        else:
            print(f"    [—] {gate} (not evaluated)")
    print()

    # Flags
    if result["flags"]:
        print(f"  Flags ({len(result['flags'])}):")
        for flag in result["flags"]:
            print(f"    ⚠  {flag}")
        print()

    # Missing fields
    if result["missing_fields"]:
        print(f"  Missing fields: {', '.join(result['missing_fields'])}")
        print()

    # Duplicates
    if result["possible_duplicates"]:
        print(f"  Possible duplicates in last {DUPLICATE_WINDOW_DAYS} days:")
        for d in result["possible_duplicates"]:
            print(f"    ↳ {d}")
        print()

    # Clearance
    print(f"  Publish clearance: {'YES' if result['publish_clearance'] else 'NO (always requires operator)'}")
    print(f"{'='*70}\n")


# ---------------------------------------------------------------------------
# Interactive input
# ---------------------------------------------------------------------------


def interactive_input() -> dict[str, Any]:
    """Collects candidate fields interactively from the terminal."""
    print("\n--- The Find Feed: New Candidate ---\n")
    candidate: dict[str, Any] = {}

    candidate["source_url"] = input("Source URL: ").strip()
    candidate["creator_name"] = input("Creator name: ").strip()
    candidate["creator_channel_url"] = input("Creator channel URL (optional): ").strip() or None
    candidate["topic_summary"] = input("Topic summary (one line): ").strip()

    print(f"Categories: {', '.join(VALID_CATEGORIES)}")
    candidate["category"] = input("Category: ").strip()

    print(f"Sensitivity levels: {', '.join(VALID_SENSITIVITY)}")
    candidate["sensitivity"] = input("Sensitivity: ").strip()

    start = input("Start time in seconds (optional): ").strip()
    end = input("End time in seconds (optional): ").strip()
    if start:
        candidate["start_time"] = float(start)
    if end:
        candidate["end_time"] = float(end)

    cutscene = input("Cutscene seconds (default 0): ").strip()
    candidate["cutscene_seconds"] = float(cutscene) if cutscene else 0.0

    candidate["claim_text"] = input("Factual claim (optional): ").strip() or None
    if candidate["claim_text"]:
        candidate["evidence_link"] = input("Evidence link for claim: ").strip() or None

    music = input("Licensed/radio music audible? (y/n, default n): ").strip().lower()
    candidate["licensed_music_audible"] = music == "y"

    candidate["game_version"] = input("Game version (e.g. 1.00): ").strip() or None
    candidate["language_spoken"] = input("Language spoken (e.g. en, ar): ").strip() or None
    candidate["notes"] = input("Notes (optional): ").strip() or None

    return {k: v for k, v in candidate.items() if v is not None}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="The Find Feed — Phase 1 Intake and Triage Tool",
        epilog="This tool validates candidates. It does not publish, download, or grant clearance.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--example",
        action="store_true",
        help="Run with a built-in sample candidate",
    )
    group.add_argument(
        "--input",
        type=str,
        metavar="FILE",
        help="Path to a candidate JSON file",
    )
    group.add_argument(
        "--interactive",
        action="store_true",
        help="Enter candidate fields interactively",
    )

    args = parser.parse_args()

    if args.example:
        candidate = SAMPLE_CANDIDATE.copy()
        print("[Using built-in sample candidate]")
    elif args.input:
        path = Path(args.input)
        if not path.exists():
            print(f"Error: file not found: {path}")
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            candidate = json.load(f)
    else:
        candidate = interactive_input()

    result = validate_candidate(candidate)
    print_result(result)

    log_path = save_candidate_log(result)
    append_run_log(result)
    print(f"  Candidate record saved: {log_path}")
    print(f"  Run log appended: {RUN_LOG_PATH}")


if __name__ == "__main__":
    main()
