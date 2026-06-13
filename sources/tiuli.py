#!/usr/bin/env python3
"""Source scraper: tiuli.com (אתר למטייל בישראל / "טיולי").

Tiuli is a Laravel site (not WordPress) fronted by Cloudflare; pages load fine
with a plain User-Agent. We take the four permanent, map-worthy categories —
attractions, points-of-interest, camping and tracks (nature walks) — and skip the
time-bound ones (events) and the species pages (flora/fauna).

Item pages live at /<category>/<numeric-id>/<slug>; the sitemap also lists region
landing pages (no numeric id) and stale entries (404), both filtered/skipped here.
Every live page carries a Waze navigation link (`...ll=<lat>,<lng>`) — the one
coordinate source present across all categories — so no geocoding is needed; a
TouristAttraction ld+json block (tracks/POIs only) supplies a clean name when
present. Emits records in the shared raw schema to data/raw/tiuli.json.
"""
import html
import json
import os
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
SITEMAP = "https://www.tiuli.com/sitemap.xml"
OUT = os.path.join(HERE, "..", "data", "raw", "tiuli.json")

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 attractions-map-builder"

# tiuli category (URL prefix) -> our shared type label. The first two reuse
# labels other sources already emit so they share a map filter; the last two are
# tiuli-specific buckets.
CATEGORY_TYPE = {
    "attractions": "אטרקציות",
    "camping": "לינת שטח - קמפינג",
    "points-of-interest": "נקודות עניין בטבע",
    "tracks": "מסלולי טיול",
}

# Israel bounding box (same guard parks.py uses) — drop anything that lands outside.
IL_BBOX = (29.0, 33.5, 34.0, 36.0)  # lat_min, lat_max, lng_min, lng_max


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def item_urls():
    """Real item pages per category: /<cat>/<id>/<slug>, de-duped by (cat, id)."""
    xml = fetch(SITEMAP)
    locs = re.findall(r"<loc>([^<]+)</loc>", xml)
    seen, out = set(), []
    for u in locs:
        m = re.match(r"https://www\.tiuli\.com/([a-z-]+)/(\d+)/", html.unescape(u))
        if not m or m.group(1) not in CATEGORY_TYPE:
            continue  # region landing pages (no numeric id) and other categories
        key = (m.group(1), m.group(2))
        if key in seen:
            continue
        seen.add(key)
        out.append((m.group(1), u))
    return out


def jsonld_attraction(html_text):
    """Return the TouristAttraction ld+json node if present (tracks/POIs carry one)."""
    for block in re.findall(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html_text, re.S
    ):
        try:
            data = json.loads(block)
        except Exception:
            continue
        for n in data if isinstance(data, list) else [data]:
            if isinstance(n, dict) and n.get("@type") == "TouristAttraction":
                return n
    return None


def meta(html_text, prop):
    m = re.search(
        r'<meta[^>]+property=["\']%s["\'][^>]+content=["\']([^"\']+)["\']' % re.escape(prop),
        html_text,
    )
    return html.unescape(m.group(1)) if m else None


def coords(html_text, node):
    """Waze link is universal; fall back to the ld+json geo when a page lacks it."""
    m = re.search(r"waze\.com/ul[^\"']*ll=([0-9.]+),([0-9.]+)", html_text)
    if m:
        return float(m.group(1)), float(m.group(2))
    geo = (node or {}).get("geo") or {}
    try:
        return float(geo["latitude"]), float(geo["longitude"])
    except (KeyError, TypeError, ValueError):
        return None, None


def clean_title(html_text, node):
    # Prefer the ld+json name (tracks/POIs); fall back to og:title. Both can carry
    # a " - <region/subtitle>" tail ("<name> - רמת הגולן - למטייל בישראל (טיולי)",
    # "הכותל המערבי - המדריך למתפלל ולמטייל"), so trim at the first " - "/"|" either way.
    raw = (node or {}).get("name") or meta(html_text, "og:title") or ""
    return re.split(r"\s+[-|]\s+", html.unescape(raw).strip())[0].strip()


def scrape(category, url):
    h = fetch(url)
    node = jsonld_attraction(h)
    lat, lng = coords(h, node)
    return {
        "source": "tiuli",
        "title": clean_title(h, node),
        "lat": lat,
        "lng": lng,
        "region": None,
        "types": [CATEGORY_TYPE[category]],
        "keywords": [],
        "image": meta(h, "og:image"),
        "url": url,
        "address": None,
        "description": None,  # on-page description is templated SEO filler; let Wikipedia fill it
    }


def main():
    items = item_urls()
    by_cat = {}
    for cat, _ in items:
        by_cat[cat] = by_cat.get(cat, 0) + 1
    print(f"{len(items)} item pages: " + ", ".join(f"{c}={n}" for c, n in sorted(by_cat.items())))

    done = {}
    if os.path.exists(OUT):
        for rec in json.load(open(OUT, encoding="utf-8")):
            done[rec["url"]] = rec
    todo = [(c, u) for c, u in items if u not in done]
    print(f"{len(done)} already scraped, {len(todo)} to do")

    results = dict(done)
    errors = gone = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(scrape, c, u): (c, u) for c, u in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            c, u = futs[fut]
            try:
                results[u] = fut.result()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    gone += 1  # stale sitemap entry — drop it
                    continue
                errors += 1
            except Exception:
                errors += 1
            if i % 200 == 0:
                print(f"  {i}/{len(todo)} (404={gone} errors={errors})")

    lo_lat, hi_lat, lo_lng, hi_lng = IL_BBOX
    out, no_coords = [], 0
    for c, u in items:
        r = results.get(u)
        if not r:
            continue  # 404 or fetch error, already counted
        if not r.get("lat") or not r.get("lng") or \
           not (lo_lat <= r["lat"] <= hi_lat and lo_lng <= r["lng"] <= hi_lng):
            no_coords += 1
            continue
        out.append(r)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"Done. {len(out)} places with coordinates "
          f"({gone} stale 404s, {no_coords} without usable coordinates, {errors} errors) -> {OUT}")


if __name__ == "__main__":
    main()
