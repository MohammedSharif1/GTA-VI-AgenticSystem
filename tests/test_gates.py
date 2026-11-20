"""Deterministic gate tests.

Covers the shipped rules plus the regressions found while verifying the repo:
an empty channel URL used to match every do-not-post row, and hard-blocked
content traits were defined in config but never checked.
"""

import pytest

from src.gates import GateValidationError, validate_job_gates


def base_job(**overrides):
    job = {
        "id": "test_01",
        "source_url": "https://example.com/clip",
        "creator_name": "FriendlyGamer",
        "start_time": 10.0,
        "end_time": 35.0,
        "sensitivity": "Green",
        "cutscene_seconds": 2.0,
        "category": "new_discovery",
    }
    job.update(overrides)
    return job


def test_valid_job_passes(sandbox):
    report = validate_job_gates(base_job())
    assert "required_fields_present" in report.passed
    assert "duration_within_limit" in report.passed
    assert "creator_opt_out_clear" in report.passed


def test_missing_channel_url_does_not_match_opt_out(sandbox):
    """Regression: an empty channel URL matched every opt-out row."""
    job = base_job()
    assert "creator_channel_url" not in job
    report = validate_job_gates(job)
    assert "creator_opt_out_clear" in report.passed


def test_empty_channel_url_with_other_creator_is_clear(sandbox):
    report = validate_job_gates(base_job(creator_channel_url=""))
    assert "creator_opt_out_clear" in report.passed


def test_excessive_duration_fails(sandbox):
    with pytest.raises(GateValidationError) as excinfo:
        validate_job_gates(base_job(start_time=0.0, end_time=45.0))
    assert "40s" in str(excinfo.value)


def test_duration_at_limit_passes(sandbox):
    report = validate_job_gates(base_job(start_time=0.0, end_time=40.0))
    assert "duration_within_limit" in report.passed


def test_reversed_window_fails(sandbox):
    with pytest.raises(GateValidationError, match="must be after"):
        validate_job_gates(base_job(start_time=20.0, end_time=10.0))


def test_non_numeric_timing_fails(sandbox):
    with pytest.raises(GateValidationError, match="must be a number of seconds"):
        validate_job_gates(base_job(start_time="fourteen", end_time=42.0))


def test_red_sensitivity_fails(sandbox):
    with pytest.raises(GateValidationError, match="Red"):
        validate_job_gates(base_job(sensitivity="Red"))


def test_unknown_sensitivity_fails(sandbox):
    with pytest.raises(GateValidationError, match="Unknown sensitivity"):
        validate_job_gates(base_job(sensitivity="Orange"))


def test_opt_out_creator_name_fails(sandbox):
    with pytest.raises(GateValidationError, match="do-not-post list"):
        validate_job_gates(base_job(creator_name="ExampleCreator"))


def test_opt_out_channel_url_fails(sandbox):
    with pytest.raises(GateValidationError, match="do-not-post list"):
        validate_job_gates(
            base_job(creator_channel_url="https://youtube.com/@example")
        )


def test_opt_out_handle_in_url_fails(sandbox):
    with pytest.raises(GateValidationError, match="do-not-post list"):
        validate_job_gates(
            base_job(
                creator_name="SomeoneElse",
                creator_channel_url="https://tiktok.com/@example_tt",
            )
        )


def test_claim_without_evidence_fails(sandbox):
    with pytest.raises(GateValidationError, match="evidence_link"):
        validate_job_gates(base_job(claim_text="Secret tunnel unlocks jetpack"))


def test_claim_with_evidence_passes(sandbox):
    report = validate_job_gates(
        base_job(
            claim_text="Secret tunnel unlocks jetpack",
            evidence_link="https://support.rockstargames.com/articles/x",
        )
    )
    assert "claim_evidence_aligned" in report.passed


@pytest.mark.parametrize(
    "trait",
    [
        "leaks_unreleased_builds",
        "cheats_mods_exploits",
        "isolated_cinematics_without_gameplay",
        "story_endings_and_major_plot_reveals",
    ],
)
def test_hard_blocked_traits_fail(sandbox, trait):
    """Regression: these traits were listed in config but never checked."""
    with pytest.raises(GateValidationError, match="hard-blocked"):
        validate_job_gates(base_job(content_flags=[trait]))


def test_cutscene_ratio_above_limit_fails(sandbox):
    with pytest.raises(GateValidationError, match="(?i)cutscene"):
        validate_job_gates(
            base_job(start_time=0.0, end_time=10.0, cutscene_seconds=3.0)
        )


def test_cutscene_ratio_at_limit_passes(sandbox):
    report = validate_job_gates(
        base_job(start_time=0.0, end_time=10.0, cutscene_seconds=2.0)
    )
    assert "cutscene_ratio_valid" in report.passed


def test_audible_music_warns_but_does_not_block(sandbox):
    report = validate_job_gates(base_job(licensed_music_audible=True))
    assert any("mute" in warning.lower() for warning in report.warnings)


def test_legacy_music_field_is_honoured(sandbox):
    report = validate_job_gates(base_job(licensed_music_present=True))
    assert any("mute" in warning.lower() for warning in report.warnings)


def test_unknown_category_fails(sandbox):
    with pytest.raises(GateValidationError, match="Unknown category"):
        validate_job_gates(base_job(category="best_of_compilation"))


def test_unknown_platform_fails(sandbox):
    with pytest.raises(GateValidationError, match="Unknown target platform"):
        validate_job_gates(base_job(platforms=["myspace"]))


def test_known_platforms_pass(sandbox):
    report = validate_job_gates(base_job(platforms=["youtube_shorts", "tiktok"]))
    assert "platforms_known" in report.passed


def test_all_failures_reported_together(sandbox):
    with pytest.raises(GateValidationError) as excinfo:
        validate_job_gates(
            base_job(
                sensitivity="Red",
                start_time=0.0,
                end_time=90.0,
                claim_text="Unverified claim",
            )
        )
    assert len(excinfo.value.failures) >= 3


def test_non_mapping_job_fails():
    with pytest.raises(GateValidationError, match="must be a mapping"):
        validate_job_gates(["not", "a", "job"])  # type: ignore[arg-type]
