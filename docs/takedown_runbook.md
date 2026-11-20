# Takedown Runbook (24-Hour SLA)

When an objection, DM, or email is received requesting removal:

1. **Acknowledge:** Reply politely confirming receipt and that the video is being taken down immediately.
2. **Execute Removal:**
   - Delete / set to private across YouTube Shorts, TikTok, Instagram Reels, and Snapchat Spotlight.
   - Target completion: within 2 hours, hard limit 24 hours.
3. **Blacklist Creator:**
   - Add creator name and all known channel URLs/handles to `config/do_not_post.csv`.
4. **Log Incident:**
   - Record in the Google Sheet `takedown_log` tab and append details to `logs/takedowns.jsonl`.
5. **Post-Mortem:**
   - Review whether any guardrail (R1-R10) was missed during screening.
