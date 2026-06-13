#!/usr/bin/env python3
"""Match places to Hebrew Wikipedia articles and fetch intro extracts.

For every place in data/attractions.json that lacks a description, run a
geosearch on he.wikipedia (https://he.wikipedia.org/w/api.php, list=geosearch)
around its coordinates, keep an article whose title fuzzy-matches the place
name, then batch-fetch intro extracts for all matches.

Output: data/enrichment/wikipedia.json — {place_title: {wp_title, url, extract}}
Resumable: already-cached place titles (including misses, stored as null) are
skipped on re-runs.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from build import name_match  # noqa: E402

PLACES = os.path.join(HERE, "..", "data", "attractions.json")
OUT = os.path.join(HERE, "..", "data", "enrichment", "wikipedia.json")

API = "https://he.wikipedia.org/w/api.php"
UA = {"User-Agent": "attractions-map-enrichment/1.0 (personal project)"}


def api_get(params, tries=5):
    qs = urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(f"{API}?{qs}", headers=UA)
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < tries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise


def find_article(place):
    """Geosearch around the place; tiered match like build.py's OSM matcher."""
    data = api_get({
        "action": "query", "list": "geosearch",
        "gscoord": f"{place['lat']}|{place['lng']}",
        "gsradius": 3000, "gslimit": 50,
    })
    best, best_score = None, 0.0
    for hit in data.get("query", {}).get("geosearch", []):
        sim = name_match(place["title"], hit["title"])
        d = hit.get("dist", 9999)
        if not (sim >= 0.85 or (sim >= 0.6 and d <= 1000)):
            continue
        score = sim - d / 10000
        if score > best_score:
            best, best_score = hit["title"], score
    return best


def fetch_extracts(titles):
    """Intro extracts, batched 20 titles per request (exlimit cap)."""
    out = {}
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        data = api_get({
            "action": "query", "prop": "extracts",
            "exintro": 1, "explaintext": 1, "exlimit": len(batch),
            "titles": "|".join(batch), "redirects": 1,
        })
        for page in data.get("query", {}).get("pages", {}).values():
            if page.get("extract"):
                out[page["title"]] = page["extract"].strip()
        time.sleep(0.1)
    return out


def main():
    places = json.load(open(PLACES, encoding="utf-8"))
    cache = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}

    todo = [p for p in places if not p.get("description") and p["title"] not in cache]
    print(f"{len(todo)} places to look up ({len(cache)} cached)")

    matched = {}
    for n, p in enumerate(todo, 1):
        try:
            wp_title = find_article(p)
        except Exception as e:
            print(f"  ! {p['title']}: {e}")
            continue
        cache[p["title"]] = {"wp_title": wp_title} if wp_title else None
        if wp_title:
            matched[p["title"]] = wp_title
        if n % 100 == 0:
            print(f"  {n}/{len(todo)} searched, {len(matched)} matched", flush=True)
            with open(OUT, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False)
        time.sleep(1.0)

    # Fill in extracts for every cached match that still lacks one.
    need = sorted({v["wp_title"] for v in cache.values() if v and "extract" not in v})
    print(f"Fetching extracts for {len(need)} articles...")
    extracts = fetch_extracts(need)
    for v in cache.values():
        if v and "extract" not in v:
            ex = extracts.get(v["wp_title"])
            if ex:
                # First ~3 sentences are enough for a popup.
                v["extract"] = " ".join(ex.split(". ")[:3]).strip()
                v["url"] = "https://he.wikipedia.org/wiki/" + urllib.parse.quote(v["wp_title"].replace(" ", "_"))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    hits = sum(1 for v in cache.values() if v and v.get("extract"))
    print(f"Done: {hits} places with Wikipedia extracts -> {OUT}")


if __name__ == "__main__":
    main()
