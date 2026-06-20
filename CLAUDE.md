# CLAUDE.md

MapTiyul: a static Leaflet map of Israel attractions. `index.html` is the whole
frontend (vanilla JS, Hebrew/RTL, CDN libs — no build step, no tests). `build.py`
merges `data/raw/*.json` into `data/attractions.js`. See `README.md` for the data
pipeline, schema, rebuild steps, and geocoding.

```bash
python3 -m http.server 8777   # open http://localhost:8777/index.html
python3 build.py              # regenerate data/attractions.{json,js} after data/raw or scraper changes
```

## Gotchas

- **`data/attractions.{js,json}` are generated** — never hand-edit; change a scraper or `data/raw/*.json` and run `build.py`. **Exception:** `tags`/`duration_min` are planning *state* held inline in `attractions.json` (filled by the `tag-places` skill / `enrich/tag_places.py`); `build.py` preserves them across rebuilds. `attractions.js` is always a generated mirror.
- **Parse `data/attractions.json`, not `.js`** — `attractions.js` is `window.ATTRACTIONS = [...];` (JS assignment, not JSON; `JSON.parse` fails). Use the `.json` twin for programmatic reads.
- **Duplicate places across sources** — the same spot appears from multiple sources at near-identical coords; dedupe by rounded coords (e.g. `lat.toFixed(3)`) when aggregating.
- **Deploy = merge to `main`** → GitHub Pages at https://amnir.github.io/maptiyul/ (absolute OG/`og:url` point there). `main` is protected: push a branch + open a PR (`gh pr create`), direct pushes are rejected. **After a PR merges, delete its feature branch** (local `git branch -D` + remote `git push origin --delete`, plus `git worktree remove` if it was a worktree) — squash merges mean `git branch -d` won't auto-detect the merge.
- **RTL layout** (`dir="rtl"`): logical CSS props are mirrored — `inline-start` = right, `inline-end` = left.
- **`sw.js` cache** `maptiyul-v1`: page + `attractions.js` are network-first; bump the cache name when changing which shell assets are precached.
- **Trip planner has two modes**: deterministic client-side generator (default, no backend) and an optional Supabase Edge Function (`supabase/functions/plan/`) for a real LLM, vendor-agnostic via `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`. The LLM path falls back to the deterministic one on any error. `SUPABASE_URL`/`SUPABASE_ANON_KEY` in `index.html` are public-by-design; real provider/service keys live only in Supabase secrets (`.env` is gitignored) — never commit them. See README "Trip planner (LLM backend)".
- **Trip-planner backend gotchas**: test the Edge Function locally without deploying (README "Local iteration"); after editing it run `supabase functions deploy plan` (deployed code lags the repo). `LLM_MODEL` must be a lean text model — a heavy multimodal/long-context model (e.g. gemma-4-31b) overruns the free Edge worker (HTTP 546). The two-call agent takes ~20–35s; the client fetch timeout is 45s — don't lower it or plans silently fall back to the deterministic planner.
