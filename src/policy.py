"""Deterministic policy loaded from ``config/``.

This module is the single source of truth for limits and blocked-content
vocabularies. Nothing in the toolchain should hardcode the 40-second excerpt
cap, the 20% cutscene cap, or the hard-blocked content list: those values live
in ``config/blocked_content.yaml`` and ``config/platform_rules.yaml`` and are
read here once.

A missing config file is a hard error. Silently falling back to defaults would
mean a misconfigured checkout quietly runs with different safety limits than
the operator reviewed.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.paths import config_path

BLOCKED_CONTENT_FILE = "blocked_content.yaml"
PLATFORM_RULES_FILE = "platform_rules.yaml"

# Editorial categories a candidate may belong to.
VALID_CATEGORIES: tuple[str, ...] = (
    "new_discovery",
    "fast_guide",
    "patch_change",
    "funny_moment",
    "other_useful",
)

# Content traits that make a candidate ineligible regardless of category.
# These are *not* categories: a candidate has a category AND may carry traits.
KNOWN_CONTENT_FLAGS: tuple[str, ...] = (
    "story_endings_and_major_plot_reveals",
    "edited_compilations_of_cutscenes_or_story_dialogue",
    "isolated_cinematics_without_gameplay",
    "cheats_mods_exploits",
    "in_game_tv_or_comedy_shows_standalone",
    "leaks_unreleased_builds",
)

SENSITIVITY_LEVELS: tuple[str, ...] = ("Green", "Yellow", "Red")
BLOCKED_SENSITIVITY = "Red"


class PolicyError(RuntimeError):
    """Raised when configuration cannot be loaded or is internally inconsistent."""


@dataclass(frozen=True)
class RuntimeLimits:
    """Hard runtime constraints from ``blocked_content.yaml``."""

    max_excerpt_seconds: float
    max_cutscene_ratio: float


@dataclass(frozen=True)
class PlatformSpec:
    """Per-platform delivery constraints from ``platform_rules.yaml``."""

    name: str
    max_duration_seconds: float
    width: int
    height: int
    top_safe_pct: float
    bottom_safe_pct: float
    right_safe_pct: float = 0.0

    @property
    def aspect_label(self) -> str:
        return f"{self.width}:{self.height}"


@dataclass(frozen=True)
class Policy:
    """The complete deterministic policy for the current checkout."""

    limits: RuntimeLimits
    hard_blocked_traits: tuple[str, ...]
    platforms: dict[str, PlatformSpec] = field(default_factory=dict)

    def platform_names(self) -> list[str]:
        return sorted(self.platforms)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PolicyError(
            f"Required config file missing: {path}. "
            "The pipeline refuses to run without its reviewed policy files."
        )
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise PolicyError(f"Config file {path} must contain a YAML mapping.")
    return data


def _parse_limits(blocked_doc: dict[str, Any], source: Path) -> RuntimeLimits:
    raw = blocked_doc.get("runtime_constraints") or {}
    try:
        max_excerpt = float(raw["max_excerpt_duration_seconds"])
        max_cutscene_pct = float(raw["max_cutscene_percentage"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PolicyError(
            f"{source} must define runtime_constraints."
            "max_excerpt_duration_seconds and max_cutscene_percentage."
        ) from exc
    if max_excerpt <= 0:
        raise PolicyError(f"{source}: max_excerpt_duration_seconds must be positive.")
    if not 0 < max_cutscene_pct <= 100:
        raise PolicyError(f"{source}: max_cutscene_percentage must be in (0, 100].")
    return RuntimeLimits(
        max_excerpt_seconds=max_excerpt,
        max_cutscene_ratio=max_cutscene_pct / 100.0,
    )


def _parse_traits(blocked_doc: dict[str, Any], source: Path) -> tuple[str, ...]:
    raw = blocked_doc.get("hard_blocked_categories") or []
    if not isinstance(raw, list) or not raw:
        raise PolicyError(f"{source} must define a non-empty hard_blocked_categories list.")
    traits = tuple(str(item).strip() for item in raw if str(item).strip())
    unknown = [t for t in traits if t not in KNOWN_CONTENT_FLAGS]
    if unknown:
        raise PolicyError(
            f"{source} contains unrecognised hard-blocked entries: {', '.join(unknown)}. "
            "Add them to KNOWN_CONTENT_FLAGS in src/policy.py so they can be matched."
        )
    return traits


def _parse_platforms(platform_doc: dict[str, Any]) -> dict[str, PlatformSpec]:
    platforms: dict[str, PlatformSpec] = {}
    for name, spec in platform_doc.items():
        if not isinstance(spec, dict):
            continue
        resolution = spec.get("resolution") or [1080, 1920]
        zones = spec.get("safe_zones") or {}
        platforms[str(name)] = PlatformSpec(
            name=str(name),
            max_duration_seconds=float(spec.get("max_duration_seconds", 60)),
            width=int(resolution[0]),
            height=int(resolution[1]),
            top_safe_pct=float(zones.get("top_margin_pct", 12)),
            bottom_safe_pct=float(zones.get("bottom_margin_pct", 18)),
            right_safe_pct=float(zones.get("right_margin_pct", 0)),
        )
    return platforms


def load_policy() -> Policy:
    """Load and validate the deterministic policy for this checkout."""
    blocked_source = config_path(BLOCKED_CONTENT_FILE)
    blocked_doc = _load_yaml(blocked_source)
    platform_doc = _load_yaml(config_path(PLATFORM_RULES_FILE))

    limits = _parse_limits(blocked_doc, blocked_source)
    traits = _parse_traits(blocked_doc, blocked_source)
    platforms = _parse_platforms(platform_doc)

    if not platforms:
        raise PolicyError("platform_rules.yaml defines no usable platform specs.")

    return Policy(limits=limits, hard_blocked_traits=traits, platforms=platforms)


def tightest_platform(policy: Policy) -> PlatformSpec:
    """The platform with the shortest duration cap.

    A single master edit must satisfy every target platform, so QA uses the
    strictest limit rather than the most permissive one.
    """
    return min(policy.platforms.values(), key=lambda p: p.max_duration_seconds)
