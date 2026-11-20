"""Arabic translation, glossary lookup, and RTL subtitle styling."""

import os
from pathlib import Path
import yaml
from typing import List, Dict, Any


def load_glossary(glossary_path: str = "config/glossary_ar.yaml") -> Dict[str, Any]:
    """Loads Arabic game glossary."""
    path = Path(glossary_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def translate_to_arabic(text: str, glossary: Dict[str, Any] = None, api_key: str = None) -> str:
    """
    Translates English gaming text to Modern Standard Arabic using GPT-4o-mini,
    preserving gaming glossary terms.
    """
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY required for translation.")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    glossary_str = yaml.dump(glossary or {}, allow_unicode=True)
    prompt = (
        "Translate the following GTA VI subtitle text into natural Modern Standard Arabic.\n"
        "Keep gaming terminology consistent with this glossary:\n"
        f"{glossary_str}\n\n"
        f"English Text:\n{text}\n\n"
        "Return ONLY the Arabic translation without markdown or explanation."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    return response.choices[0].message.content.strip()


def generate_arabic_ass_subtitles(segments: List[Dict[str, Any]], output_path: str, font_name: str = "Noto Sans Arabic") -> str:
    """
    Generates ASS (Advanced SubStation Alpha) subtitle file formatted for RTL Arabic text,
    ensuring correct rendering via FFmpeg libass.
    """
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ArabicDefault,{font_name},52,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,40,40,380,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def format_ass_ts(seconds: float) -> str:
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centis = int((seconds - int(seconds)) * 100)
        return f"{hrs:d}:{mins:02d}:{secs:02d}.{centis:02d}"

    events = []
    for seg in segments:
        start = format_ass_ts(seg["start"])
        end = format_ass_ass = format_ass_ts(seg["end"])
        text = seg["text"].strip().replace("\n", " ")
        events.append(f"Dialogue: 0,{start},{end},ArabicDefault,,0,0,0,,{text}")

    full_ass = header + "\n".join(events) + "\n"
    with open(out_p, "w", encoding="utf-8") as f:
        f.write(full_ass)

    return str(out_p)
