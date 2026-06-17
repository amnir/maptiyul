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
- **Deploy = merge to `main`** → GitHub Pages at https://amnir.github.io/maptiyul/ (absolute OG/`og:url` point there). `main` is protected: push a branch + open a PR (`gh pr create`), direct pushes are rejected.
- **RTL layout** (`dir="rtl"`): logical CSS props are mirrored — `inline-start` = right, `inline-end` = left.
- **`sw.js` cache** `maptiyul-v1`: page + `attractions.js` are network-first; bump the cache name when changing which shell assets are precached.
