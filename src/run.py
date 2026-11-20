"""Pipeline runner CLI.

    python -m src.run check                       # environment + policy facts
    python -m src.run job jobs/example_job.yaml   # render one job
    python -m src.run job JOB --dry-run           # gate + plan, no encoding

``python src/run.py`` also works: the bootstrap below puts the repository root
on ``sys.path`` so the ``src.`` package imports resolve either way.
"""

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.job import JobError, load_job  # noqa: E402
from src.pipeline import (  # noqa: E402
    STATUS_BLOCKED,
    STATUS_SUCCESS,
    RenderResult,
    environment_report,
    render_job,
)


def _print_environment() -> int:
    report = environment_report()
    print("The Find Feed — environment")
    print("=" * 60)
    for tool, version in report["ffmpeg"].items():
        print(f"  {tool:<8} {version}")
    limits = report["limits"]
    if "error" in limits:
        print(f"  policy    ERROR: {limits['error']}")
        return 1
    print(f"  excerpt   max {limits['max_excerpt_seconds']:.0f}s (R2)")
    print(f"  cutscene  max {limits['max_cutscene_ratio']:.0%} of excerpt (R9)")
    print(
        f"  tightest  {limits['tightest_platform']} "
        f"({limits['tightest_max_duration']:.0f}s)"
    )
    print(f"  platforms {', '.join(report['platforms'])}")
    print()
    print("  Publish clearance is never granted by this toolchain.")
    return 0


def _print_result(result: RenderResult, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result.to_log(), ensure_ascii=False, indent=2))
    else:
        print()
        print("=" * 70)
        print(f"  Job {result.job_id} — {result.status}")
        print("=" * 70)
        for stage in result.stages:
            print(f"  [{stage.status:<8}] {stage.name}: {stage.detail}")
        for warning in result.warnings:
            print(f"  warning: {warning}")
        if result.error:
            print(f"  error: {result.error}")
        if result.output_path:
            print(f"  output: {result.output_path}")
        print(f"  audio muted (R10): {'yes' if result.audio_muted else 'no'}")
        print("  publish clearance: NO (always requires the operator)")
        print("=" * 70)

    if result.status == STATUS_SUCCESS:
        return 0
    if result.status == STATUS_BLOCKED:
        return 2
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="The Find Feed pipeline runner",
        epilog="Rendering is not publishing. This tool never grants clearance.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Report FFmpeg and policy status")

    job_parser = subparsers.add_parser("job", help="Render a job YAML")
    job_parser.add_argument("job_file", help="Path to a job YAML file")
    job_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the gates and describe the plan without encoding",
    )
    job_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the structured result as JSON",
    )

    args = parser.parse_args(argv)

    if args.command == "check":
        return _print_environment()

    try:
        job = load_job(args.job_file)
    except JobError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    result = render_job(job, dry_run=args.dry_run)
    return _print_result(result, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
