"""Main pipeline runner CLI."""

import argparse
import json
from pathlib import Path
import time
import yaml
from dotenv import load_dotenv

from src.gates import validate_job_gates, GateValidationError
from src.cut import cut_excerpt
from src.reframe import reframe_9_16
from src.credit import generate_credit_text, burn_credit_overlay

load_dotenv()


def log_run(log_data: dict, log_path: str = "logs/runs.jsonl"):
    """Appends structured log to runs.jsonl."""
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_data, ensure_ascii=False) + "\n")


def execute_job(job_file: str):
    """Executes the v1 pipeline on a single job YAML."""
    start_time_all = time.time()
    job_path = Path(job_file)
    if not job_path.exists():
        raise FileNotFoundError(f"Job file not found: {job_file}")

    with open(job_path, "r", encoding="utf-8") as f:
        job = yaml.safe_load(f)

    job_id = job.get("id", job_path.stem)
    print(f"[*] Processing Job ID: {job_id}")

    # 1. Gate validation
    print("  -> Checking deterministic gates...")
    try:
        passed_gates = validate_job_gates(job)
        print(f"     [OK] All gates passed: {', '.join(passed_gates)}")
    except GateValidationError as e:
        print(f"     [FAIL] Gate validation blocked job: {e}")
        log_run({
            "job_id": job_id,
            "status": "BLOCKED",
            "error": str(e),
            "timestamp": time.time()
        })
        return False

    source_file = job.get("source_file")
    if not source_file or not Path(source_file).exists():
        print(f"     [INFO] Source file '{source_file}' not found locally.")
        print("     Place raw footage at specified path to complete render.")
        log_run({
            "job_id": job_id,
            "status": "AWAITING_SOURCE_FILE",
            "source_path": source_file,
            "timestamp": time.time()
        })
        return True

    # 2. Excerpt Cut
    out_dir = Path("out") / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    cut_file = out_dir / "cut.mp4"
    print(f"  -> Cutting excerpt ({job['start_time']}s - {job['end_time']}s)...")
    cut_excerpt(source_file, str(cut_file), float(job["start_time"]), float(job["end_time"]))

    # 3. Reframe 9:16
    reframe_file = out_dir / "reframe_9_16.mp4"
    print("  -> Reframing to 1080x1920 (9:16)...")
    reframe_9_16(str(cut_file), str(reframe_file))

    # 4. Credit Overlay
    final_en = out_dir / f"{job_id}_final_en.mp4"
    credit_text = generate_credit_text(job["creator_name"])
    print(f"  -> Adding on-screen credit: '{credit_text}'...")
    burn_credit_overlay(str(reframe_file), str(final_en), credit_text)

    duration_total = time.time() - start_time_all
    print(f"[*] Render complete in {duration_total:.2f}s -> {final_en}")

    log_run({
        "job_id": job_id,
        "status": "SUCCESS",
        "output_file": str(final_en),
        "execution_seconds": duration_total,
        "cost_usd": 0.0,
        "timestamp": time.time()
    })
    return True


def main():
    parser = argparse.ArgumentParser(description="The Find Feed Pipeline Runner")
    subparsers = parser.add_subparsers(dest="command")

    job_parser = subparsers.add_parser("job", help="Run a specific job YAML")
    job_parser.add_argument("job_file", help="Path to job YAML file")

    args = parser.parse_args()
    if args.command == "job":
        execute_job(args.job_file)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
