"""Unit tests for deterministic safety and rights gates."""

import pytest
from src.gates import validate_job_gates, GateValidationError


def test_valid_job():
    job = {
        "id": "test_01",
        "source_url": "https://example.com/clip",
        "creator_name": "FriendlyGamer",
        "start_time": 10.0,
        "end_time": 35.0,
        "sensitivity": "Green",
        "cutscene_seconds": 2.0,
        "licensed_music_present": False,
    }
    passed = validate_job_gates(job)
    assert "required_fields_present" in passed
    assert "duration_within_limit" in passed


def test_excessive_duration_fails():
    job = {
        "id": "test_02",
        "source_url": "https://example.com/clip",
        "creator_name": "FriendlyGamer",
        "start_time": 0.0,
        "end_time": 45.0,  # Exceeds 40s
        "sensitivity": "Green",
    }
    with pytest.raises(GateValidationError, match="exceeds max 40.0s"):
        validate_job_gates(job)


def test_red_sensitivity_fails():
    job = {
        "id": "test_03",
        "source_url": "https://example.com/clip",
        "creator_name": "FriendlyGamer",
        "start_time": 0.0,
        "end_time": 20.0,
        "sensitivity": "Red",
    }
    with pytest.raises(GateValidationError, match="Red"):
        validate_job_gates(job)


def test_opt_out_creator_fails():
    job = {
        "id": "test_04",
        "source_url": "https://example.com/clip",
        "creator_name": "ExampleCreator",  # In do_not_post.csv
        "start_time": 0.0,
        "end_time": 20.0,
        "sensitivity": "Green",
    }
    with pytest.raises(GateValidationError, match="do-not-post list"):
        validate_job_gates(job)


def test_claim_without_evidence_fails():
    job = {
        "id": "test_05",
        "source_url": "https://example.com/clip",
        "creator_name": "FriendlyGamer",
        "start_time": 0.0,
        "end_time": 20.0,
        "sensitivity": "Green",
        "claim_text": "Secret tunnel unlocks jetpack",
        # missing evidence_link
    }
    with pytest.raises(GateValidationError, match="evidence_link"):
        validate_job_gates(job)
