#!/usr/bin/env python3
"""Curated source: indoor play venues for small kids (פעלטון-style משחקיות,
ג'ימבורי, soft-play), hand-maintained in sources/kidsfun_venues.json.

Unlike the scraped sources, this one is a verified editorial list: every venue
carries opening hours (Saturday matters most — these are the places that ARE
open on Shabbat when the heritage/nature corpus is closed) and an age range.
Coordinates are geocoded via Nominatim (mall name first, then street address),
cached in sources/cache/kidsfun_geocode.json, and sanity-checked against the
venue's city centroid so a bad geocode can't land a branch in the wrong town.

Emits the shared raw schema to data/raw/kidsfun.json with hours/phone/website
passed through (build.py's merge copies those fields from raw members).
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENUES = os.path.join(HERE, "kidsfun_venues.json")
CACHE = os.path.join(HERE, "cache", "kidsfun_geocode.json")
OUT = os.path.join(ROOT, "data", "raw", "kidsfun.json")

UA = "attractions-map-builder/1.0 (amara.nir@gmail.com)"
LAT_MIN, LAT_MAX = 29.45, 33.40
LON_MIN, LON_MAX = 34.20, 35.95
KIDSFUN_TYPE = "משחקיות ובילוי מקורה"

_last_req = [0.0]


def _nominatim(params):
    wait = 1.1 - (time.time() - _last_req[0])
    if wait > 0:
        time.sleep(wait)
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    _last_req[0] = time.time()
    return data


def geocode(query):
    # Two attempts: countrycodes=il first, then a bounded viewbox without it —
    # West Bank places (e.g. Maale Adumim) aren't tagged 'il' in Nominatim.
    for params in (
        {"q": query, "countrycodes": "il", "format": "json", "limit": "1",
         "viewbox": f"{LON_MIN},{LAT_MAX},{LON_MAX},{LAT_MIN}"},
        {"q": query, "format": "json", "limit": "1", "bounded": "1",
         "viewbox": f"{LON_MIN},{LAT_MAX},{LON_MAX},{LAT_MIN}"},
    ):
        data = _nominatim(params)
        if not data:
            continue
        lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
        if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
            return {"lat": lat, "lng": lon, "display": data[0].get("display_name", "")}
    return None


def geocode_city(city):
    data = _nominatim({
        "city": city, "format": "json", "limit": "1",
        "viewbox": f"{LON_MIN},{LAT_MAX},{LON_MAX},{LAT_MIN}", "bounded": "1",
    })
    if not data:
        return None
    return {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"])}


def dist_km(a, b):
    import math
    dlat = (a["lat"] - b["lat"]) * 111.0
    dlng = (a["lng"] - b["lng"]) * 111.0 * math.cos(math.radians((a["lat"] + b["lat"]) / 2))
    return math.hypot(dlat, dlng)


def load_cache():
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    return {}


def main():
    venues = json.load(open(VENUES, encoding="utf-8"))
    cache = load_cache()

    def cached(key, fn, *args):
        if key not in cache:
            try:
                cache[key] = fn(*args)
            except Exception:
                cache[key] = None
        return cache[key]

    out, misses = [], []
    for v in venues:
        city = v["city"]
        # Mall name resolves to the exact building; the street address and the
        # venue name are progressively weaker fallbacks.
        queries = []
        if v.get("geocode_hint"):
            queries.append(v["geocode_hint"])
        if v.get("mall"):
            queries.append(f"{v['mall']}, {city}")
        if v.get("address"):
            queries.append(f"{v['address']}, {city}")
        queries.append(f"{v['title']}, {city}")

        geo = None
        for q in queries:
            geo = cached(q, geocode, q)
            if not geo:
                continue
            centroid = cached("city:" + city, geocode_city, city)
            # Reject hits far from the stated city (same-named mall/street in
            # another town); 12km covers metro sprawl like Beer Sheva.
            if centroid and dist_km(geo, centroid) > 12:
                geo = None
                continue
            break
        if not geo:
            misses.append(v["title"])
            continue

        hours = v.get("hours")
        keywords = ["משחקייה", "ילדים", "בילוי מקורה"] + v.get("keywords", [])
        # "Sa <time>" (not "Sa off") ⇒ open on Shabbat — the killer search term.
        if hours and re.search(r"Sa[^;]*\d", hours) and not re.search(r"Sa (off|closed)", hours):
            keywords.append("פתוח בשבת")

        out.append({
            "source": "kidsfun",
            "title": v["title"],
            "lat": round(geo["lat"], 6),
            "lng": round(geo["lng"], 6),
            "region": None,  # build.py derives from coords
            "types": [KIDSFUN_TYPE],
            "keywords": keywords,
            "image": v.get("image"),
            "url": v["url"],
            "address": f"{v['address']}, {city}" if v.get("address") else city,
            "description": v.get("description"),
            "hours": v.get("hours"),
            "phone": v.get("phone"),
            "website": v.get("website") or v["url"],
        })

    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"kidsfun: {len(out)} venues placed -> {OUT}")
    if misses:
        print(f"  {len(misses)} could not be geocoded: " + "; ".join(misses))


if __name__ == "__main__":
    main()
