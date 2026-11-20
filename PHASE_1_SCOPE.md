# The Find Feed — Phase 1 Scope

This document records the confirmed decisions, boundaries, and acceptance criteria
for Phase 1 of The Find Feed project.

## What Phase 1 is

A local intake and triage tool (`src/find_feed.py`) that:

- Accepts manually entered candidate metadata (JSON file, interactive prompt, or built-in sample).
- Validates required fields and deterministic rules.
- Checks for possible duplicate topics from the previous 7 days.
- Flags risks (sensitivity, missing evidence, blocked creators, licensed music).
- Writes structured candidate records and run logs.
- Never grants publish clearance — `publish_clearance` is always `False`.

## What Phase 1 is NOT

- It does not download or process source media.
- It does not contact creators or platforms.
- It does not publish or authorize publication.
- It does not use paid APIs or services.
- It is not an autonomous AI agent.

## Confirmed operator decisions

| Area | Decision |
|---|---|
| Operator | One person, running on own computer |
| Source mix | Public creator clips, official Rockstar material, own tips/finds |
| Permission model | Permission must be secured **before** public posting (editing may start while pending) |
| Categories | new_discovery, fast_guide, patch_change, funny_moment, other_useful |
| Languages | English and Arabic (Modern Standard Arabic) |
| Narration | AI voiceover where appropriate; retain creator speech as subtitles, don't replace it |
| Source audio | Mute when radio/music is audible |
| Duplicate check | Manual check of topics covered in previous 7 days |
| Excerpt limit | Maximum 40 seconds of source footage |
| Budget | $90/month total tools cap (planning estimate) |
| Volume | 2–4 shorts/day target (planning estimate) |
| Rights approach | Proceed under Rockstar's published content policy, accepting uncertainty |

## Unresolved gates (not decided by this tool or operator yet)

1. **Rights and monetization mismatch:** The published-policy route may not cover recurring or monetized use. Keep rights clearance out of the tool's authority.
2. **Source-file acquisition:** The approved method for obtaining third-party video files is not set. Do not add downloading or screen recording.
3. **Contacting Take-Two:** Whether and when to contact Take-Two is undecided.
4. **Creator outreach, compensation, account setup, removal email, backup coverage:** All undecided.

## Deterministic gates enforced by the tool

| Gate | Rule | Blocks? |
|---|---|---|
| Required fields | source_url, creator_name, topic_summary, category, sensitivity | Yes (needs_review) |
| Valid category | Must be one of the five defined categories | Yes (needs_review) |
| Sensitivity | Red = blocked in current phase | Yes (blocked) |
| Excerpt duration | ≤ 40 seconds | Yes (blocked) |
| Cutscene ratio | ≤ 20% of excerpt duration | Yes (blocked) |
| Claim-evidence | Claim without evidence link = flagged | Yes (needs_review) |
| Licensed music | Flagged if music/radio audible | Yes (needs_review) |
| Do-not-post list | Creator on opt-out list = blocked | Yes (blocked) |
| Duplicate check | Advisory only — operator decides | No |
| Permission | Always flagged as reminder | No (operator responsibility) |
| Publish clearance | Always False | — |

## Phase 1 acceptance criteria

An operator can:
1. Enter a candidate manually.
2. Receive a candidate record with missing fields and risk flags.
3. See any possible repeat from the previous 7 days.
4. Understand that the output is not publication clearance.
5. The program does not fetch, upload, or publish any content.

## What comes next (not in Phase 1)

- Media pipeline (FFmpeg cut, reframe, subtitles, credit overlay, voiceover) — code exists in `src/` but is not invoked by Phase 1.
- Arabic translation pipeline — code exists in `src/arabic.py` but is not invoked by Phase 1.
- Platform publishing and scheduling.
- Workflow engine and AI agents (LangGraph, trigger-based).
- Observability (Langfuse).
