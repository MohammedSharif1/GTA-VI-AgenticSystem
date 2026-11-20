# The Find Feed — GTA VI Clips System

Automated vertical video pipeline turning verified public GTA VI moments and official Rockstar updates into short-form content for YouTube Shorts, TikTok, Instagram Reels, and Snapchat Spotlight in English and Arabic (Modern Standard Arabic).

Based on Plan Revision 5.

## Project Structure

```text
find-feed/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── jobs/                   # YAML job files defining clips to process
├── out/                    # Rendered vertical videos
├── logs/
│   └── runs.jsonl          # Structured execution logs with per-job cost & timing
├── config/
│   ├── platform_rules.yaml # Platform specifications & limits
│   ├── blocked_content.yaml# Rockstar policy & hard-blocked topics
│   ├── glossary_ar.yaml    # Standardized Arabic terms & transliterations
│   ├── series_templates.yaml# Series structure & timings (New Find, Fast Guide, What Changed)
│   └── do_not_post.csv     # Creator opt-out / blacklist with multi-platform handles
├── src/
│   ├── __init__.py
│   ├── cut.py              # Excerpt cutting via FFmpeg
│   ├── reframe.py          # 9:16 vertical smart crop and HUD handling
│   ├── subtitles.py        # Speech-to-text (Whisper API) & subtitle generation
│   ├── arabic.py           # Arabic translation, glossary lookup & RTL libass formatting
│   ├── credit.py           # On-screen credit overlay generation
│   ├── gates.py            # Hard programmatic validation checks (R1-R10)
│   └── run.py              # Main CLI orchestrator (`python -m src.run job jobs/<file>.yaml`)
├── docs/
│   ├── rights_rules.md     # R1-R10 guardrails and rights stance
│   ├── attribution.md      # Caption and on-screen credit templates
│   ├── takedown_runbook.md # 24-hour removal workflow
│   └── dm_templates.md     # English and Arabic outreach notification templates
└── tests/
    ├── __init__.py
    └── test_gates.py       # Unit tests for deterministic validation rules
```

## Quick Start

1. Install Python 3.11+ and ensure `ffmpeg` with `libass` is installed and in your system PATH.
2. Install dependencies:
   ```bash
   pip install -e .
   ```
3. Copy `.env.example` to `.env` and fill in your `OPENAI_API_KEY`.
4. Create a job YAML file in `jobs/` (see `jobs/example_job.yaml`).
5. Run the pipeline:
   ```bash
   python -m src.run job jobs/example_job.yaml
   ```
