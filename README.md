# מפת אתרים ואטרקציות בישראל — Attractions Map

An interactive map of family attractions in Israel, built from multiple sources.
Browse every place on a map and filter by **type** (attractions, parks, viewpoints,
springs, water trips, animals, visitor centers, camping, coffee carts, and more),
by **region**, and by **source**.

**Sources**
- [familytrips.co.il](https://familytrips.co.il) — בשביל המשפחה (family trips & attractions)
- [coffeetrail.co.il](https://coffeetrail.co.il) — Coffee Trail (coffee-cart directory)

Places that appear in more than one source are merged into a single marker that
links back to every source.

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
counts, region pills, free-text search (name / keyword), and popups that link back
to the original article.

## Architecture

Each source has its own scraper that writes records in a shared schema to
`data/raw/<source>.json`. A single `build.py` then merges every source, de-dups
co-located places, and writes the final dataset the map reads.

```
scrape/*.py  (familytrips: scrape + geocode)  ─┐
sources/coffeetrail.py                         ─┤→ data/raw/*.json → build.py → data/attractions.js
                                                ┘                                       ↑ index.html
```

**Shared record schema** (`data/raw/*.json`):
`source, title, lat, lng, region|null, types[], keywords[], image, url, address|null, description|null`

### Rebuild

```bash
# familytrips (needs geocoding — see notes):
python3 scrape/1_collect_urls.py
python3 scrape/2_scrape_posts.py
python3 scrape/3_geocode.py          # -> data/raw/familytrips.json

# coffeetrail (coordinates already in the pages):
python3 sources/coffeetrail.py       # -> data/raw/coffeetrail.json

# merge + de-dup -> data/attractions.json + data/attractions.js
python3 build.py
```

### Adding another source

Write a `sources/<name>.py` that emits `data/raw/<name>.json` in the shared schema
(set `lat`/`lng` if you have them, otherwise leave the place name for geocoding),
add a label to `SOURCE_LABELS` in `build.py`, and re-run `build.py`. The map picks
up the new source filter automatically.

### Notes

- **familytrips** pages carry no coordinates (each embeds a Google map keyed by the
  place *name*), so `3_geocode.py` geocodes names via the free Nominatim service
  (no API key) at ~1 req/sec — ~25–35 min, resumable via `data/geocode_cache.json`.
  It tries several query variants (HTML-unescaped, trimmed at the first dash,
  leading descriptors like "גן לאומי" stripped, Plus-Code locality) and keeps the
  first hit inside Israel. A minority of obscure spots can't be resolved and are dropped.
- **coffeetrail** listings expose exact coordinates + address in a `LocalBusiness`
  schema, so no geocoding is needed.
- **De-dup** (`build.py`) only merges across *different* sources, and requires both
  proximity and a fuzzy name match — so distinct attractions that geocode to the same
  town centroid, and different branches of the same coffee brand, stay separate.
- **Region** uses each source's own tags when present, otherwise latitude bands
  (with a Jerusalem bounding box).
