"""Font discovery for burned-in text.

FFmpeg's ``drawtext`` filter needs a concrete font file on Windows, where
libfontconfig is usually absent from the static builds. Rather than failing
with an opaque "Cannot find a valid font" error, resolve a file up front and
let the operator point at a specific one with ``FIND_FEED_FONT``.

Arabic captions need a font with Arabic glyph coverage, so
``prefer_arabic=True`` puts those candidates first.
"""

import os
from pathlib import Path

FONT_ENV_VAR = "FIND_FEED_FONT"

LATIN_FONTS = (
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)

ARABIC_FONTS = (
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


class FontNotFoundError(RuntimeError):
    """Raised when no usable font file can be located."""


def resolve_font(prefer_arabic: bool = False) -> Path:
    """Return a font file suitable for burned-in text."""
    override = os.getenv(FONT_ENV_VAR)
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_file():
            raise FontNotFoundError(
                f"{FONT_ENV_VAR} points at a missing font file: {candidate}"
            )
        return candidate

    ordered = (ARABIC_FONTS + LATIN_FONTS) if prefer_arabic else (LATIN_FONTS + ARABIC_FONTS)
    for raw in ordered:
        candidate = Path(raw)
        if candidate.is_file():
            return candidate

    raise FontNotFoundError(
        "No font file found for burned-in text. Set "
        f"{FONT_ENV_VAR} to the full path of a .ttf or .otf file."
    )


def ffmpeg_font_path(font: Path) -> str:
    """Render a font path for use inside an FFmpeg filter argument.

    FFmpeg's filter parser treats ``:`` as an option separator and ``\\`` as an
    escape, so a Windows path must be slash-separated with the drive colon
    escaped.
    """
    return str(font).replace("\\", "/").replace(":", "\\:")
