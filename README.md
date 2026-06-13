# מפת אתרים ואטרקציות בישראל — Attractions Map

An interactive map of family attractions in Israel, built from multiple sources.
Browse every place on a map and filter by **type** (attractions, parks, viewpoints,
springs, water trips, animals, visitor centers, camping, coffee carts, and more),
by **region**, and by **source**.

**Sources**
- [familytrips.co.il](https://familytrips.co.il) — בשביל המשפחה (family trips & attractions)
- [coffeetrail.co.il](https://coffeetrail.co.il) — Coffee Trail (coffee-cart directory)
- [parks.org.il](https://www.parks.org.il) — רשות הטבע והגנים (national parks & nature reserves)

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
