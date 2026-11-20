"""Opt-out matching tests.

The empty-value regression lives here because that is where the bug was: a
missing channel URL normalised to ``""`` and ``"" in value`` is always true,
so every candidate matched every opt-out row.
"""

from src.optout import (
    OptOutEntry,
    find_opt_out_match,
    handle_segments,
    load_opt_out_list,
    normalize_handle,
    normalize_url,
)

ENTRY = OptOutEntry(
    creator_name="ExampleCreator",
    urls=("youtube.com/@example",),
    handles=("example_tt", "example_ig", "example_x"),
    reason="Explicit opt-out request",
)


def test_normalize_url_strips_scheme_and_trailing_slash():
    assert normalize_url("https://www.YouTube.com/@Example/") == "youtube.com/@example"


def test_normalize_handle_strips_at_sign():
    assert normalize_handle("  @Example_IG ") == "example_ig"


def test_normalize_url_of_empty_input_is_empty():
    assert normalize_url("") == ""
    assert normalize_url(None) == ""


def test_handle_segments_extracts_handle_from_url():
    segments = handle_segments("https://youtube.com/@ViceCityExplorer")
    assert "vicecityexplorer" in segments


def test_missing_channel_url_never_matches():
    """Regression: absent fields must not match anything."""
    assert find_opt_out_match("FriendlyGamer", None, [ENTRY]) is None
    assert find_opt_out_match("FriendlyGamer", "", [ENTRY]) is None


def test_absent_creator_name_never_matches():
    assert find_opt_out_match(None, None, [ENTRY]) is None
    assert find_opt_out_match("", "", [ENTRY]) is None


def test_matches_by_name_case_insensitively():
    match = find_opt_out_match("  examplecreator ", None, [ENTRY])
    assert match is not None
    assert match.matched_on == "creator name"


def test_matches_by_url():
    match = find_opt_out_match("Someone", "https://youtube.com/@example", [ENTRY])
    assert match is not None
    assert match.matched_on == "channel URL"


def test_matches_by_handle_inside_url():
    match = find_opt_out_match("Someone", "https://tiktok.com/@example_tt", [ENTRY])
    assert match is not None
    assert "example_tt" in match.matched_on


def test_non_matching_creator_is_clear():
    assert (
        find_opt_out_match(
            "FriendlyGamer", "https://youtube.com/@friendlygamer", [ENTRY]
        )
        is None
    )


def test_empty_list_matches_nothing():
    assert find_opt_out_match("ExampleCreator", None, []) is None


def test_load_does_not_raise_on_missing_file(tmp_path):
    assert load_opt_out_list(tmp_path / "absent.csv") == []


def test_load_skips_blank_rows(tmp_path):
    path = tmp_path / "list.csv"
    path.write_text(
        "creator_name,youtube_url,tiktok_handle,instagram_handle,twitter_handle,"
        "reason,date_added\n"
        ",,,,,,\n"
        "RealCreator,,,,,asked us not to,2026-01-01\n",
        encoding="utf-8",
    )
    entries = load_opt_out_list(path)
    assert len(entries) == 1
    assert entries[0].creator_name == "RealCreator"
    assert entries[0].reason == "asked us not to"


def test_load_handles_short_rows(tmp_path):
    """A row with fewer columns yields None values; matching must not crash."""
    path = tmp_path / "list.csv"
    path.write_text(
        "creator_name,youtube_url,tiktok_handle\nShortRow\n",
        encoding="utf-8",
    )
    entries = load_opt_out_list(path)
    assert entries[0].creator_name == "ShortRow"
    assert find_opt_out_match("ShortRow", None, entries) is not None
