# מפת אתרים ואטרקציות בישראל — Attractions Map

An interactive map of family attractions in Israel, built from multiple sources.
Browse every place on a map and filter by **type** (attractions, parks, viewpoints,
springs, water trips, animals, visitor centers, camping, coffee carts, and more),
by **region**, and by **source**.

**Sources**
- [familytrips.co.il](https://familytrips.co.il) — בשביל המשפחה (family trips & attractions)
- [coffeetrail.co.il](https://coffeetrail.co.il) — Coffee Trail (coffee-cart directory)
- [parks.org.il](https://www.parks.org.il) — רשות הטבע והגנים (national parks & nature reserves)
- [tiuli.com](https://www.tiuli.com) — אתר למטייל בישראל / טיולי (attractions, points of
  interest, camping & nature-walk trails)

Places that appear in more than one source are merged into a single marker that
links back to every source.

Markers are then **enriched** from free open data: opening hours, phone, website,
wheelchair access and entry fee from **OpenStreetMap**, and a short description +
article link from **Hebrew Wikipedia**. Each place popup also shows a **live
weather forecast** ([Open-Meteo](https://open-meteo.com), fetched in the browser).

## Using the map

The map data is baked into a JavaScript file, so you can just open it:

```bash
open index.html        # macOS — double-clicking also works
```

If your browser blocks the local data file, serve the folder instead:

```bash
python3 -m http.server 8777
# then visit http://localhost:8777/index.html
```

Features: marker clustering, color-coded markers by region, type checkboxes with
counts, region pills, free-text search (name / keyword), an accessibility (נגישות)
filter, near-me distance sorting, favorites, shareable URLs, and popups that show
hours / phone / fee / weather and link back to the original article, the official
site and Wikipedia.

## Architecture

Each source has its own scraper that writes records in a shared schema to
`data/raw/<source>.json`. A single `build.py` then merges every source, de-dups
co-located places, enriches them from OpenStreetMap + Wikipedia, and writes the
final dataset the map reads.

```
scrape/*.py  (familytrips: scrape + geocode)  ─┐
sources/coffeetrail.py                         ─┤→ data/raw/*.json ─┐
sources/parks.py                               ─┘                   │
                                                                    ▼
enrich/osm.py       → data/enrichment/osm_pois.json  ──→  build.py  ──→  data/attractions.js
enrich/wikipedia.py → data/enrichment/wikipedia.json ──↗                        ↑ index.html
```

**Shared record schema** (`data/raw/*.json`):
`source, title, lat, lng, region|null, types[], keywords[], image, url, address|null, description|null`
Sources may also supply `hours, phone, website, fee` directly (parks does); otherwise
`build.py` fills those from OpenStreetMap. The final records additionally carry
`wikipedia|null` and an `accessible` flag.

### Rebuild

```bash
# familytrips (needs geocoding — see notes):
python3 scrape/1_collect_urls.py
python3 scrape/2_scrape_posts.py
python3 scrape/3_geocode.py          # -> data/raw/familytrips.json

# coffeetrail (coordinates already in the pages):
python3 sources/coffeetrail.py       # -> data/raw/coffeetrail.json

# parks (reads sources/cache/parks_raw.json — see notes):
python3 sources/parks.py             # -> data/raw/parks.json

# tiuli (coordinates already in the pages; resumable):
python3 sources/tiuli.py             # -> data/raw/tiuli.json

# enrichment (optional but recommended; both are resumable):
python3 enrich/osm.py                # -> data/enrichment/osm_pois.json (one bulk Overpass query)
python3 enrich/wikipedia.py          # -> data/enrichment/wikipedia.json (~1 req/sec, ~20 min)

# merge + de-dup + enrich -> data/attractions.json + data/attractions.js
python3 build.py
```

### Adding another source

Write a `sources/<name>.py` that emits `data/raw/<name>.json` in the shared schema
(set `lat`/`lng` if you have them, otherwise leave the place name for geocoding),
add a label to `SOURCE_LABELS` in `build.py`, and re-run `build.py`. The map picks
up the new source filter automatically.

### Notes

- **familytrips** pages carry no coordinates, but most embed a Google Plus Code
  (e.g. `WX8H+V4 מודיעין מכבים רעות`), which `3_geocode.py` decodes to the exact
  spot (via the vendored `scrape/openlocationcode.py`): full codes directly, short
  codes recovered against the locality, looked up with Nominatim's structured
  settlement search (bounded to the Israel bbox rather than `countrycodes=il`, so
  West Bank localities resolve; transliterated names retried with apostrophes
  stripped). Posts without a plus code fall back to free-text name geocoding with
  several query variants (HTML-unescaped, trimmed at the first dash, leading
  descriptors like "גן לאומי" stripped), keeping the first hit inside Israel —
  these may land on a town centre. Nominatim is free (no API key) at ~1 req/sec,
  resumable via `data/geocode_cache.json`. A minority of obscure spots can't be
  resolved and are dropped.
- **coffeetrail** listings expose exact coordinates + address in a `LocalBusiness`
  schema, so no geocoding is needed.
- **parks** comes from the site's WordPress REST API (`/wp-json/wp/v2/rp`). The site
  is behind CloudFront and blocks scripted requests, so the raw dump is fetched once
  in a browser and saved to `sources/cache/parks_raw.json`; `sources/parks.py` then
  converts its ITM / Israeli TM Grid coordinates (EPSG:2039) to WGS84 and maps the
  site's filter flags to our types.
- **tiuli** is a Laravel site (not WordPress) behind Cloudflare but reachable with a
  plain User-Agent. `sources/tiuli.py` walks the one `sitemap.xml`, keeps only real
  item pages (`/<category>/<id>/<slug>` for attractions, points-of-interest, camping
  and tracks — region landing pages and the stale 404 entries are skipped), and reads
  each page's Waze navigation link (`…ll=<lat>,<lng>`) for coordinates — the one source
  present across every category, so no geocoding. Events (time-bound) and flora/fauna
  (species pages) are intentionally excluded. The on-page description is templated SEO
  filler, so it is left blank for Wikipedia enrichment to fill.
- **OSM enrichment** (`enrich/osm.py`) issues a single bulk Overpass query for named
  POIs across Israel, and `build.py` copies hours/phone/website/wheelchair/fee onto a
  place only on a confident name+distance match (a wrong match would show another
  business's details). A strong name match also snaps a geocoded place to the POI's
  exact coordinates.
- **Wikipedia enrichment** (`enrich/wikipedia.py`) runs a Hebrew-Wikipedia geosearch
  around each place lacking a description and keeps a fuzzy-name-matched article.
  Because a geosearch near a descriptive trail/forest name tends to return the
  *nearest settlement*, `build.py` drops any extract that reads as a village profile
  unless the attraction's name essentially equals the article name.
- **De-dup** (`build.py`) only merges across *different* sources, and requires both
  proximity and a fuzzy name match — so distinct attractions that geocode to the same
  town centroid, and different branches of the same coffee brand, stay separate. An
  identical (non-coffee) name merges across a wider radius, since one source may pin
  the entrance and another the town centroid.
- **Region** uses each source's own tags when present, otherwise latitude bands
  (with a Jerusalem bounding box).

## Trip planner (LLM backend)

The "סוכן תכנון הטיולים" planner has two modes. By default it runs the deterministic,
client-side generator in `index.html` (no backend, works on GitHub Pages as-is). If a
Supabase Edge Function is configured, it instead runs a real free-text agent, falling
back to the deterministic generator on any error — so the feature never hard-breaks.

**How the agent works** (`supabase/functions/plan/index.ts`): the client sends only the
free-text request (e.g. *"אני מרמת גן, רוצה טיול חצי יום בשרון"*). The function owns the
dataset (fetched warm-cached from the published `data/attractions.json`) and runs two
model calls: (A) parse the text into `{origin, area, duration, prefs}` using the model's
own knowledge of Israeli geography for coordinates; then it filters the dataset to the
area and (B) selects/orders stops + writes Hebrew copy. Geometry stays deterministic —
candidates are filtered by haversine and the chosen stops are ordered by projection onto
the origin→area axis (so a trip from Ramat Gan into the Sharon runs south→north). Stops
are resolved back to real pins by index (no coordinate hallucination); the client only
computes times/legs and renders.

The model layer is **vendor-agnostic**: the function talks to any OpenAI-compatible
`/v1/chat/completions` endpoint (NVIDIA NIM, Groq, OpenRouter, Together, local Ollama…)
via three env vars — swap the provider with no code change. Prefer a lean text model:
heavy multimodal/long-context models (e.g. Gemma-4-31B VLM) can exceed the free Edge
worker's limit (HTTP 546).

**What's committed vs. secret** (this repo is public):

- *Committed:* the function code (`supabase/functions/plan/index.ts`), the client glue
  in `index.html`, the Supabase **project URL + anon key** (public by design — the anon
  key is meant to ship in the frontend), and `supabase/functions/plan/.env.example`
  (names only).
- *Never committed:* the real `LLM_API_KEY` and the Supabase `service_role` key. These
  live only as Supabase secrets. `.env` is gitignored.

**Setup** (one-time, all manual — needs a free Supabase project and a model provider):

```bash
supabase login
supabase init                     # if supabase/config.toml doesn't exist yet
supabase link --project-ref <ref> # from your Supabase project's dashboard URL

# set the provider secrets (real values, never committed):
cp supabase/functions/plan/.env.example supabase/functions/plan/.env
# edit .env → LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
supabase secrets set --env-file supabase/functions/plan/.env

supabase functions deploy plan    # deploys the Edge Function
```

Then paste your project URL and anon key into `SUPABASE_URL` / `SUPABASE_ANON_KEY`
near the top of the trip-planner IIFE in `index.html`. Leaving them blank keeps the
deterministic planner. The endpoint is currently open (anon key only); add rate
limiting before relying on a paid provider.

**Local iteration (no deploy).** The pipeline lives in `supabase/functions/plan/pipeline.ts`
as a pure `planTrip(body, env, deps)`; `index.ts` is just the `Deno.serve` HTTP wrapper.
To try prompt/model changes against the real provider without `supabase functions deploy`,
run the CLI harness — it loads `supabase/functions/plan/.env` and pretty-prints the plan
with per-leg haversine distances and the coffee count:

```bash
brew install deno   # if Deno isn't installed
deno run --allow-net --allow-env --allow-read \
  supabase/functions/plan/dev.ts "אני מרמת גן, רוצה טיול חצי יום בשרון" [half|full]
```

Zero-code alternative — serve the function locally over HTTP (also reads `.env`, no deploy):

```bash
supabase functions serve --env-file supabase/functions/plan/.env
# then POST {"query":"…","duration":"half"} to the printed localhost URL
```
