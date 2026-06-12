#!/usr/bin/env python3
"""Geocode each post's place name to coordinates and build data/attractions.json.

Uses OpenStreetMap Nominatim (free, no key). Respects 1 req/sec. Resumable via
a query cache so re-runs only fetch new/failed queries.
"""
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request

import openlocationcode as olc

HERE = os.path.dirname(__file__)
POSTS = os.path.join(HERE, "..", "data", "posts.json")
CACHE = os.path.join(HERE, "..", "data", "geocode_cache.json")
OUT = os.path.join(HERE, "..", "data", "raw", "familytrips.json")

UA = "attractions-map-builder/1.0 (amara.nir@gmail.com)"
# Israel bounding box (lat/lon) used to reject bad geocodes.
LAT_MIN, LAT_MAX = 29.45, 33.40
LON_MIN, LON_MAX = 34.20, 35.95

# Region category tokens that may appear in articleSection; mapped to a clean region.
REGION_TOKENS = {
    "צפון": "צפון",
    "מרכז": "מרכז",
    "דרום": "דרום",
    "ירושלים": "ירושלים",
    "ירושלים והסביבה": "ירושלים",
    "ירושלים ומדבר יהודה": "ירושלים",
    "מרכז הארץ": "מרכז",
    "מרכז וסובב ירושלים": "מרכז",
}


def load_cache():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


# Leading descriptor words; stripping them often yields a cleaner place name
# (e.g. "גן לאומי כורזים" -> "כורזים") that Nominatim resolves.
PREFIXES = [
    "גן לאומי", "הגן הלאומי", "שמורת הטבע", "שמורת טבע", "פארק וגן לאומי",
    "אתר טבע", "פארק לאומי",
]
# Google Plus Code, optionally followed by a locality name we can geocode instead.
PLUS_RE = re.compile(r"^([23456789CFGHJMPQRVWX]{2,}\+[23456789CFGHJMPQRVWX]+)\s*(.*)$")


def clean(s):
    if not s:
        return ""
    s = html.unescape(s)
    # drop descriptive suffix after a dash / pipe separator
    s = re.split(r"\s[–—|-]\s", s)[0]
    return s.strip()


def query_variants(mapq, title):
    out = []

    def add(q):
        q = (q or "").strip()
        if q and q not in out:
            out.append(q)

    for raw in (mapq, title):
        if not raw:
            continue
        m = PLUS_RE.match(html.unescape(raw).strip())
        if m and m.group(2):
            add(m.group(2))          # locality after the plus code
            continue
        if m:
            continue                  # bare plus code, can't geocode by name
        c = clean(raw)
        add(c)
        for p in PREFIXES:
            if c.startswith(p + " "):
                add(c[len(p):].strip())
    return out


def plus_code_parts(raw):
    """Return (code, locality) if raw starts with a plus code, else None."""
    m = PLUS_RE.match(html.unescape(raw or "").strip())
    if not m:
        return None
    return m.group(1), m.group(2).strip(" ,")


def geocode_place(locality):
    """Structured settlement search for a plus-code locality. Free-text search
    often ranks same-named streets in other cities first, which would recover
    the short code in the wrong grid cell. No countrycodes filter: West Bank
    settlements (e.g. Kalia) aren't tagged 'il'; the viewbox bounds instead.
    Transliterated names only match OSM with apostrophes removed (Yavne'el ->
    Yavneel), so retry without them."""
    variants = [locality]
    stripped = locality.replace("'", "").replace("’", "")
    if stripped != locality:
        variants.append(stripped)
    for n, variant in enumerate(variants):
        if n:
            time.sleep(1.1)
        params = urllib.parse.urlencode({
            "city": variant,
            "format": "json",
            "limit": "3",
            "viewbox": f"{LON_MIN},{LAT_MAX},{LON_MAX},{LAT_MIN}",
            "bounded": "1",
        })
        url = "https://nominatim.openstreetmap.org/search?" + params
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        for d in data:
            if d.get("class") not in ("place", "boundary"):
                continue
            lat, lon = float(d["lat"]), float(d["lon"])
            if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
                return {"lat": lat, "lng": lon, "display": d.get("display_name", "")}
    return None


def decode_plus_code(code, ref):
    """Exact coordinates from a plus code. Full codes decode directly; short
    codes (e.g. "WX8H+V4") are recovered against the locality geocode, which
    only needs to be within ~25km of the true spot."""
    try:
        if olc.isFull(code):
            full = code
        elif ref and olc.isShort(code):
            full = olc.recoverNearest(code, ref["lat"], ref["lng"])
        else:
            return None
        area = olc.decode(full)
    except ValueError:
        return None
    lat, lng = area.latitudeCenter, area.longitudeCenter
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lng <= LON_MAX):
        return None
    return {"lat": lat, "lng": lng, "display": f"plus code {code}"}


def geocode(query):
    params = urllib.parse.urlencode({
        "q": query,
        "countrycodes": "il",
        "format": "json",
        "limit": "1",
        "viewbox": f"{LON_MIN},{LAT_MAX},{LON_MAX},{LAT_MIN}",
    })
    url = "https://nominatim.openstreetmap.org/search?" + params
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if not data:
        return None
    lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return None
    return {"lat": lat, "lng": lon, "display": data[0].get("display_name", "")}


def region_from_lat(lat):
    if lat >= 32.5:
        return "צפון"
    if lat >= 31.55:
        return "מרכז"
    return "דרום"


def split_types(tokens):
    region = None
    types = []
    for t in tokens:
        if t in REGION_TOKENS:
            region = REGION_TOKENS[t]
        else:
            types.append(t)
    # dedupe types, keep order
    seen, uniq = set(), []
    for t in types:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return region, uniq


def main():
    with open(POSTS, encoding="utf-8") as f:
        posts = json.load(f)
    cache = load_cache()

    # Build unique query list (mapq preferred, title fallback handled per-post later).
    candidates = [p for p in posts if p.get("mapq")]
    print(f"{len(posts)} posts, {len(candidates)} with a place query")

    attractions = []
    misses = 0
    requests_made = 0
    for i, p in enumerate(candidates, 1):
        queries = query_variants(p.get("mapq"), p.get("title"))

        geo = None
        for q in queries:
            if q in cache:
                geo = cache[q]
            else:
                try:
                    geo = geocode(q)
                except Exception as e:
                    geo = None
                cache[q] = geo
                requests_made += 1
                time.sleep(1.1)
                if requests_made % 50 == 0:
                    save_cache(cache)
                    print(f"  {i}/{len(candidates)} processed, {requests_made} requests, {len(attractions)} placed, {misses} misses")
            if geo:
                break

        # A plus code in mapq pins the exact spot; a geocoded locality only
        # serves as the reference point for recovering short codes.
        plus = plus_code_parts(p.get("mapq"))
        if plus:
            code, locality = plus
            ref = geo
            if locality and olc.isShort(code):
                key = "city:" + locality
                if key in cache:
                    place = cache[key]
                else:
                    try:
                        place = geocode_place(locality)
                    except Exception:
                        place = None
                    cache[key] = place
                    requests_made += 1
                    time.sleep(1.1)
                ref = place or geo
            exact = decode_plus_code(code, ref)
            if exact:
                geo = exact

        if not geo:
            misses += 1
            continue

        region, types = split_types(p.get("types", []))
        if not region:
            region = region_from_lat(geo["lat"])
        attractions.append({
            "source": "familytrips",
            "title": html.unescape(p["title"]),
            "lat": round(geo["lat"], 6),
            "lng": round(geo["lng"], 6),
            "region": region,
            "types": types,
            "keywords": [html.unescape(k) for k in p.get("keywords", [])],
            "image": p.get("image"),
            "url": p["url"],
            "address": None,
            "description": None,
        })

    save_cache(cache)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(attractions, f, ensure_ascii=False)
    print(f"Done. {len(attractions)} placed, {misses} could not be geocoded -> {OUT}")
    print("Run `python3 build.py` to merge all sources and rebuild the map data.")


if __name__ == "__main__":
    main()
