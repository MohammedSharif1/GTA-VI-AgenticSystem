"""Shared test fixtures.

Tests never write into the real ``logs/`` or ``out/`` directories: the
``FIND_FEED_ROOT`` variable redirects the path helpers at a temporary
checkout that contains only the config files the code needs to read.
"""

import shutil
from pathlib import Path

import pytest

from src import paths

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILES = ("blocked_content.yaml", "platform_rules.yaml", "do_not_post.csv")


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point the toolchain at an isolated temp checkout with real configs."""
    config_source = REPO_ROOT / "config"
    config_target = tmp_path / "config"
    config_target.mkdir()
    for name in CONFIG_FILES:
        source = config_source / name
        if source.exists():
            shutil.copy2(source, config_target / name)

    (tmp_path / "logs").mkdir()
    (tmp_path / "out").mkdir()

    monkeypatch.setenv(paths.ROOT_ENV_VAR, str(tmp_path))
    return tmp_path


@pytest.fixture
def isolated_opt_out(tmp_path, monkeypatch):
    """A do-not-post list built by the test, not the shipped one."""
    from src import optout

    path = tmp_path / "do_not_post.csv"
    path.write_text(
        "creator_name,youtube_url,tiktok_handle,instagram_handle,twitter_handle,"
        "reason,date_added\n"
        "ExampleCreator,https://youtube.com/@example,@example_tt,@example_ig,"
        "@example_x,Explicit opt-out request,2026-11-20\n",
        encoding="utf-8",
    )
    entries = optout.load_opt_out_list(path)
    return entries
