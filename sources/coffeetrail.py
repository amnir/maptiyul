#!/usr/bin/env python3
"""Source scraper: coffeetrail.co.il coffee-cart directory.

Each /coffeecart/<slug>/ listing carries a LocalBusiness ld+json block with
exact coordinates and an address, so no geocoding is needed. Emits records in
the shared raw schema to data/raw/coffeetrail.json.
"""
import html
import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(__file__)
SITEMAP = "https://coffeetrail.co.il/job_listing-sitemap.xml"
OUT = os.path.join(HERE, "..", "data", "raw", "coffeetrail.json")

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 attractions-map-builder"
TYPE = "עגלות קפה ופוד טראק"  # same label familytrips uses, so they share a filter


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def listing_urls():
    xml = fetch(SITEMAP)
    urls = re.findall(r"<loc>([^<]+)</loc>", xml)
    return [u for u in urls if "/coffeecart/" in u]


def find_local_business(html_text):
    for block in re.findall(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html_text, re.S
    ):
        try:
            data = json.loads(block)
        except Exception:
            continue
        graph = data.get("@graph") if isinstance(data, dict) else None
        nodes = graph if isinstance(graph, list) else (data if isinstance(data, list) else [data])
        for n in nodes:
            if not isinstance(n, dict):
                continue
            t = n.get("@type")
            types = t if isinstance(t, list) else [t]
            if "LocalBusiness" in types:
                return n
    return None


def meta(html_text, prop):
    m = re.search(
        r'<meta[^>]+property=["\']%s["\'][^>]+content=["\']([^"\']+)["\']' % re.escape(prop),
        html_text,
    )
    return m.group(1) if m else None


def scrape(url):
    h = fetch(url)
    lb = find_local_business(h) or {}
    geo = lb.get("geo") or {}
    try:
        lat = float(geo.get("latitude"))
        lng = float(geo.get("longitude"))
    except (TypeError, ValueError):
        lat = lng = None

    addr = lb.get("address")
    if isinstance(addr, dict):
        addr = addr.get("address") or addr.get("streetAddress")

    title = lb.get("name") or (meta(h, "og:title") or "").split("|")[0].strip()
    desc = lb.get("description")
    if isinstance(desc, str):
        desc = re.sub(r"<[^>]+>", "", html.unescape(desc)).strip()

    return {
        "source": "coffeetrail",
        "title": html.unescape(title or "").strip(),
        "lat": lat,
        "lng": lng,
        "region": None,
        "types": [TYPE],
        "keywords": [],
        "image": meta(h, "og:image"),
        "url": url,
        "address": html.unescape(addr) if isinstance(addr, str) else None,
        "description": desc or None,
    }


def main():
    urls = listing_urls()
    print(f"{len(urls)} coffee-cart listings")

    done = {}
    if os.path.exists(OUT):
        for rec in json.load(open(OUT, encoding="utf-8")):
            done[rec["url"]] = rec
    todo = [u for u in urls if u not in done]
    print(f"{len(done)} already scraped, {len(todo)} to do")

    results = dict(done)
    errors = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(scrape, u): u for u in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            u = futs[fut]
            try:
                results[u] = fut.result()
            except Exception as e:
                errors += 1
                results[u] = {"source": "coffeetrail", "url": u, "title": "", "lat": None,
                              "lng": None, "types": [TYPE], "keywords": [], "image": None,
                              "region": None, "address": None, "error": str(e)}
            if i % 100 == 0:
                print(f"  {i}/{len(todo)} (errors={errors})")

    out = [results[u] for u in urls if u in results]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    placed = sum(1 for r in out if r.get("lat") and r.get("lng"))
    print(f"Done. {len(out)} listings, {placed} with coordinates, {errors} errors -> {OUT}")


if __name__ == "__main__":
    main()
