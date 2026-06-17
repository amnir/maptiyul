---
name: tag-places
description: Fill planning tags + duration_min for attractions missing them, writing into data/attractions.json (the canonical state) and regenerating attractions.js. Use after new places are scraped/added, or when the trip planner needs tags for untagged places.
---

# tag-places

Tags live as **state directly in `data/attractions.json`** — there is no separate
tags file. This skill fills planning attributes for any place that is **missing**
them; it never overwrites existing tags (those are curated/authoritative).

## Schema

Each tagged place gains two fields, inline in `attractions.json`:

- **`tags`** — array from a controlled vocabulary:
  `indoor`, `outdoor`, `kid-friendly`, `scenic`, `rainy-day-ok`, `food`, `quick-stop`, `nature`, `beach`.
  Grow the vocabulary deliberately (edit `VOCAB` in `enrich/tag_places.py`) — a new
  dimension is a vocab entry, not a schema change. `tags` is a planning layer; it
  does **not** replace `types[]` (the Hebrew source taxonomy behind the user filters).
- **`duration_min`** — integer; the planner sums it for scheduling. Never a tag.

## Steps

1. **See what's untagged:**
   ```bash
   python3 enrich/tag_places.py --list
   ```
2. **Fill the missing ones** (rule-based baseline, writes `.json` + regenerates `.js`):
   ```bash
   python3 enrich/tag_places.py
   ```
3. **Hand-correct the ambiguous ones.** The rules are coarse — `indoor` especially
   is keyword-guessed. Scan the newly-tagged places (focus on `אטרקציות` with no
   clear signal) and fix any wrong `indoor`/`outdoor`/`duration_min` by editing the
   record **directly in `data/attractions.json`**, then regenerate the JS mirror:
   ```bash
   python3 enrich/tag_places.py   # re-running is safe; it only fills empties
   ```
   (To force a re-tag of a specific place, delete its `tags` in `attractions.json`
   first, or just edit the values in place.)

## Notes

- `attractions.json` is the single source of truth. `attractions.js` is a generated
  mirror (`window.ATTRACTIONS = …`) for the no-build browser load — never edit it by hand.
- `build.py` **preserves** these tags across rebuilds (it carries `tags`/`duration_min`
  from the previous `attractions.json` by source URL), so re-scraping won't wipe them.
- The trip planner (`index.html`) reads `a.tags` / `a.duration_min` and falls back to
  coarse inference only where a place is still untagged.
