# Rights Rules

These rules apply to every candidate and short produced by **The Find Feed**.

## Permission model

**Permission must be secured before public posting.** Editing may start while permission is pending, but nothing is published until the operator has documented permission or is using material that fits the selected rights approach.

This tool does not check, grant, or verify permission. `publish_clearance` is always `False`.

## Guardrails

- **R1. Public sources only:** Skip any creator whose channel or profile states no re-uploads or clipping, or who has asked not to be used.
- **R2. Use the moment, not the video:** Excerpt only the necessary seconds. Max 40 seconds of source footage and never a full video.
- **R3. Add original value:** Every short must contain original on-screen elements — hook text, context, labels, closing insight, or commentary.
- **R4. Credit and removal contact:** Display on-screen source credit and caption credit. Never state or imply permission or endorsement.
- **R5. Permission before posting:** Obtain written or documented permission from the creator before publishing. Do not post and notify after the fact.
- **R6. Removal on request:** On any creator objection, remove the video across all platforms within 24 hours and permanently add their handle to `config/do_not_post.csv`.
- **R7. Hard stop rule:** Any copyright strike, Content ID match, claim, or notice from Take-Two/Rockstar immediately pauses all posting pending full review.
- **R8. No misleading edits:** Never alter what the creator said or meant. Every factual claim requires a verified evidence link.
- **R9. Hard-blocked content:** Strictly adhere to `config/blocked_content.yaml` (no leaks, no isolated cutscenes, no major story endings, no cheats/mods/exploits).
- **R10. Licensed music:** If licensed radio music is audible, mute the audio segment before production.

## Sensitivity levels

| Level | Content | Handling |
|---|---|---|
| Green | Exploration, scenery, vehicles, UI, non-violent gameplay | Standard |
| Yellow | Mild violence, mild language, suggestive themes | Age/sensitivity settings where available |
| Red | Graphic violence, strong language, sexual content, drug use | Not posted in current phase |

## Unresolved rights questions

These are not decided by this document:

- Whether the operation fits Rockstar's published content policy for recurring/monetized use.
- The approved method for obtaining third-party source files.
- Whether and when to contact Take-Two.
- Creator compensation terms.
