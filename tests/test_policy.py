"""Policy loader tests.

The loader exists because the shipped config files were never read by any code:
the 40-second and 20% limits were duplicated as constants in two modules, and
the hard-blocked content list was dead. These tests pin the contract.
"""

import pytest

from src import paths
from src.paths import config_path
from src.policy import (
    PolicyError,
    VALID_CATEGORIES,
    load_policy,
    tightest_platform,
)

MINIMAL_PLATFORMS = (
    "youtube_shorts:\n  max_duration_seconds: 60\n  resolution: [1080, 1920]\n"
)


def write_config(tmp_path, blocked_body: str) -> None:
    """Create a temp checkout containing exactly the files the loader reads."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "blocked_content.yaml").write_text(blocked_body, encoding="utf-8")
    (config_dir / "platform_rules.yaml").write_text(
        MINIMAL_PLATFORMS, encoding="utf-8"
    )


def test_loads_shipped_policy():
    policy = load_policy()
    assert policy.limits.max_excerpt_seconds == 40.0
    assert policy.limits.max_cutscene_ratio == pytest.approx(0.20)


def test_loads_every_platform():
    policy = load_policy()
    assert set(policy.platforms) == {
        "youtube_shorts",
        "tiktok",
        "instagram_reels",
        "snapchat_spotlight",
    }


def test_platform_resolution_is_vertical():
    policy = load_policy()
    for spec in policy.platforms.values():
        assert spec.height > spec.width
        assert spec.top_safe_pct > 0


def test_tightest_platform_is_the_shortest_cap():
    policy = load_policy()
    tightest = tightest_platform(policy)
    shortest = min(p.max_duration_seconds for p in policy.platforms.values())
    assert tightest.max_duration_seconds == shortest


def test_hard_blocked_traits_are_loaded_from_config():
    policy = load_policy()
    assert "leaks_unreleased_builds" in policy.hard_blocked_traits
    assert "cheats_mods_exploits" in policy.hard_blocked_traits


def test_missing_config_is_a_hard_error(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ROOT_ENV_VAR, str(tmp_path))
    with pytest.raises(PolicyError, match="missing"):
        load_policy()


def test_inconsistent_limits_are_rejected(tmp_path, monkeypatch):
    write_config(
        tmp_path,
        "hard_blocked_categories:\n  - leaks_unreleased_builds\n"
        "runtime_constraints:\n  max_excerpt_duration_seconds: 0\n"
        "  max_cutscene_percentage: 20\n",
    )
    monkeypatch.setenv(paths.ROOT_ENV_VAR, str(tmp_path))
    with pytest.raises(PolicyError, match="must be positive"):
        load_policy()


def test_unknown_blocked_trait_is_rejected(tmp_path, monkeypatch):
    """A typo in config must fail loudly rather than silently stop blocking."""
    write_config(
        tmp_path,
        "hard_blocked_categories:\n  - typo_entry\n"
        "runtime_constraints:\n  max_excerpt_duration_seconds: 40\n"
        "  max_cutscene_percentage: 20\n",
    )
    monkeypatch.setenv(paths.ROOT_ENV_VAR, str(tmp_path))
    with pytest.raises(PolicyError, match="unrecognised"):
        load_policy()


def test_categories_are_the_documented_five():
    assert len(VALID_CATEGORIES) == 5
    assert "new_discovery" in VALID_CATEGORIES


def test_shipped_config_files_exist():
    assert config_path("blocked_content.yaml").is_file()
    assert config_path("platform_rules.yaml").is_file()
    assert config_path("do_not_post.csv").is_file()
