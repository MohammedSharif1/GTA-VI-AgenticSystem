"""Creator opt-out (do-not-post) list matching.

A single implementation shared by intake (``find_feed``) and the render gates.
The two earlier copies diverged, and the gates copy treated an empty channel
URL as matching every opt-out row, because ``"" in value`` is always true. That
blocked every job that did not carry a channel URL.

Matching is deliberately conservative in the safe direction: an entry matches
on a normalised creator name, on a normalised URL, or on a handle that appears
as a path segment of the candidate's channel URL. An absent field never
matches anything.
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from src.paths import config_path

DO_NOT_POST_FILE = "do_not_post.csv"

NAME_COLUMN = "creator_name"
URL_COLUMN = "youtube_url"
HANDLE_COLUMNS = ("tiktok_handle", "instagram_handle", "twitter_handle")
REASON_COLUMN = "reason"

_URL_PREFIXES = ("https://", "http://", "www.")


@dataclass(frozen=True)
class OptOutEntry:
    """One row of ``config/do_not_post.csv``."""

    creator_name: str
    urls: tuple[str, ...]
    handles: tuple[str, ...]
    reason: str

    @property
    def label(self) -> str:
        return self.creator_name or "(unnamed entry)"


@dataclass(frozen=True)
class OptOutMatch:
    """A candidate matched against the opt-out list."""

    entry: OptOutEntry
    matched_on: str

    def describe(self) -> str:
        reason = self.entry.reason or "unspecified"
        return (
            f"Creator '{self.entry.label}' is on the do-not-post list "
            f"(matched on {self.matched_on}, reason: {reason})."
        )


def normalize_name(value: str | None) -> str:
    """Lowercase, whitespace-collapsed creator name."""
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def normalize_url(value: str | None) -> str:
    """Comparable form of a URL: no scheme, no ``www.``, no trailing slash."""
    if not value:
        return ""
    text = value.strip().lower()
    changed = True
    while changed:
        changed = False
        for prefix in _URL_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):]
                changed = True
    parsed = urlparse("//" + text)
    host_path = f"{parsed.netloc}{parsed.path}".rstrip("/")
    return host_path.split("?", 1)[0]


def normalize_handle(value: str | None) -> str:
    """Comparable form of a social handle: lowercase, no leading ``@``."""
    if not value:
        return ""
    return value.strip().lower().lstrip("@")


def handle_segments(channel_url: str | None) -> set[str]:
    """Handle-like tokens contained in a channel URL.

    ``https://youtube.com/@ViceCityExplorer`` yields both
    ``vicecityexplorer`` and the full normalised URL path, so a stored handle
    can be found without comparing a bare handle against a whole URL.
    """
    if not channel_url:
        return set()
    normalized = normalize_url(channel_url)
    if not normalized:
        return set()
    segments: set[str] = set()
    path = normalized.split("/", 1)[1] if "/" in normalized else ""
    for raw_segment in path.split("/"):
        segment = raw_segment.strip()
        if not segment:
            continue
        segments.add(segment)
        segments.add(normalize_handle(segment))
    segments.discard("")
    return segments


def _split_handles(entry: OptOutEntry) -> set[str]:
    return {handle for handle in entry.handles if handle}


def load_opt_out_list(path: Path | str | None = None) -> list[OptOutEntry]:
    """Load the do-not-post list. A missing file means an empty list."""
    source = Path(path) if path is not None else config_path(DO_NOT_POST_FILE)
    if not source.exists():
        return []

    entries: list[OptOutEntry] = []
    with open(source, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get(NAME_COLUMN) or "").strip()
            url = normalize_url(row.get(URL_COLUMN))
            handles = tuple(
                normalized
                for normalized in (
                    normalize_handle(row.get(column)) for column in HANDLE_COLUMNS
                )
                if normalized
            )
            reason = (row.get(REASON_COLUMN) or "").strip()
            if not name and not url and not handles:
                # Blank or malformed row: nothing identifiable to match on.
                continue
            entries.append(
                OptOutEntry(
                    creator_name=name,
                    urls=(url,) if url else (),
                    handles=handles,
                    reason=reason,
                )
            )
    return entries


def find_opt_out_match(
    creator_name: str | None,
    channel_url: str | None,
    entries: list[OptOutEntry],
) -> OptOutMatch | None:
    """Return the first matching opt-out entry, or ``None`` if the candidate is clear."""
    normalized_name = normalize_name(creator_name)
    normalized_url = normalize_url(channel_url)
    segments = handle_segments(channel_url)

    for entry in entries:
        if normalized_name and normalize_name(entry.creator_name) == normalized_name:
            return OptOutMatch(entry=entry, matched_on="creator name")

        if normalized_url:
            for entry_url in entry.urls:
                if not entry_url:
                    continue
                if entry_url == normalized_url:
                    return OptOutMatch(entry=entry, matched_on="channel URL")
                # Handle short forms such as "youtube.com/@name" vs
                # "youtube.com/@name/videos" without matching empty strings.
                if entry_url in normalized_url or normalized_url in entry_url:
                    return OptOutMatch(entry=entry, matched_on="channel URL")

        if segments:
            overlap = segments & _split_handles(entry)
            if overlap:
                return OptOutMatch(
                    entry=entry, matched_on=f"handle {sorted(overlap)[0]}"
                )

    return None
