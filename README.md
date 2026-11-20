# The Find Feed — GTA VI Clips System

A one-person operation for finding interesting GTA VI moments — discoveries, fast guides, patch changes, funny moments, and other useful finds — and producing short vertical videos for YouTube Shorts, TikTok, Instagram Reels, and Snapchat Spotlight, in English and Arabic.

## Current phase: Phase 1 — Intake and Triage

The active tool is `src/find_feed.py`. It accepts manually entered candidate metadata, validates fields against deterministic rules, checks for duplicate topics, flags risks, and writes structured logs. It does not download media, contact creators, publish, or grant clearance.

See [PHASE_1_SCOPE.md](PHASE_1_SCOPE.md) for the full scope, confirmed decisions, and acceptance criteria.

## Quick start

```bash
# Run with the built-in sample candidate
python src/find_feed.py --example

# Process a candidate from a JSON file
python src/find_feed.py --input candidate.json

# Enter candidate fields interactively
python src/find_feed.py --interactive
```

**Requirements:** Python 3.11+ (standard library only — no paid services or API keys needed for Phase 1).

## Project structure

```text
find-feed/
├── README.md                   # This file
├── PHASE_1_SCOPE.md            # Phase 1 scope, decisions, and acceptance criteria
├── pyproject.toml              # Python project config
├── .env.example                # Environment variable template (Phase 2+)
├── .gitignore
├── src/
│   ├── find_feed.py            # ← Phase 1 intake/triage tool (active)
│   ├── cut.py                  # FFmpeg excerpt cutting (Phase 2+)
│   ├── reframe.py              # 9:16 vertical reframing (Phase 2+)
│   ├── subtitles.py            # Whisper transcription & SRT (Phase 2+)
│   ├── arabic.py               # Arabic translation & RTL subtitles (Phase 2+)
│   ├── credit.py               # Credit overlay generation (Phase 2+)
│   ├── gates.py                # Pipeline gate validation (Phase 2+)
│   └── run.py                  # Pipeline runner CLI (Phase 2+)
├── config/
│   ├── platform_rules.yaml     # Platform specs & limits
│   ├── blocked_content.yaml    # Hard-blocked categories
│   ├── glossary_ar.yaml        # Arabic gaming terms glossary
│   ├── series_templates.yaml   # Series structure & timings
│   └── do_not_post.csv         # Creator opt-out list
├── docs/
│   ├── rights_rules.md         # R1-R10 guardrails
│   ├── attribution.md          # Credit templates (EN & AR)
│   ├── takedown_runbook.md     # 24-hour removal workflow
│   └── dm_templates.md         # Creator outreach templates
├── jobs/                       # YAML job files (Phase 2+)
├── logs/
│   ├── candidates/             # Phase 1 candidate records (JSON)
│   └── runs.jsonl              # Structured run log
└── tests/
    └── test_gates.py           # Gate validation tests
```

## Key rules

- **Permission before posting:** Permission must be secured before public posting. Editing may start while permission is pending.
- **Source excerpt:** Maximum 40 seconds, never a full video.
- **Cutscene limit:** At most 20% of a short's runtime.
- **Source audio:** Mute whenever radio or licensed music is audible.
- **Credit:** On-screen source credit on every short. No ownership claims.
- **Publish clearance:** Always requires the operator. The tool never authorizes publication.
