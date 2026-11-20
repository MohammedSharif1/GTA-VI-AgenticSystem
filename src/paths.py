"""Repository-anchored filesystem paths.

Every tool resolves config, log, and output locations relative to the project
root rather than the current working directory, so commands behave identically
whether they are run from the repository root, `src/`, or a test runner.

Set the ``FIND_FEED_ROOT`` environment variable to point the tools at a
different checkout (used by the test suite to isolate writes).
"""

import os
from pathlib import Path

ROOT_ENV_VAR = "FIND_FEED_ROOT"


def project_root() -> Path:
    """Absolute path to the repository root."""
    override = os.getenv(ROOT_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    # src/paths.py -> src/ -> repository root
    return Path(__file__).resolve().parents[1]


def config_dir() -> Path:
    return project_root() / "config"


def config_path(filename: str) -> Path:
    return config_dir() / filename


def logs_dir() -> Path:
    return project_root() / "logs"


def candidates_dir() -> Path:
    return logs_dir() / "candidates"


def runs_log_path() -> Path:
    return logs_dir() / "runs.jsonl"


def out_dir() -> Path:
    return project_root() / "out"


def data_dir() -> Path:
    return project_root() / "data"


def jobs_dir() -> Path:
    return project_root() / "jobs"


def ensure_parent(path: Path) -> Path:
    """Create the parent directory of ``path`` if needed and return ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
