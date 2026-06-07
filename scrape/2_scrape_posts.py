#!/usr/bin/env python3
"""Fetch each post and extract title, map place-query, type tags, image, link.

Writes data/posts.json (list of dicts). Resumable: skips URLs already scraped.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(__file__)
URLS = os.path.join(HERE, "..", "data", "urls.txt")
OUT = os.path.join(HERE, "..", "data", "posts.json")

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 attractions-map-builder"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def extract_ldjson_article(html):
    for block in re.findall(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S
    ):
        try:
            data = json.loads(block)
        except Exception:
            continue
        graph = data.get("@graph", []) if isinstance(data, dict) else []
        for node in graph:
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Article" in types or "BlogPosting" in types:
                return node
    return None


def meta(html, prop):
    m = re.search(
        r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]+content=["\']([^"\']+)["\']'
        % re.escape(prop),
        html,
    )
    return m.group(1) if m else None


def scrape(url):
    html = fetch(url)
    art = extract_ldjson_article(html) or {}

    title = art.get("headline") or meta(html, "og:title")
    if not title:
        m = re.search(r"<title>([^<|]+)", html)
        title = m.group(1).strip() if m else None

    # google maps embed keyed by place name: maps.google.com/maps?q=<place>
    mapq = None
    mm = re.search(r"maps\.google\.com/maps\?q=([^&\"'<>]+)", html)
    if mm:
        mapq = urllib.parse.unquote(mm.group(1)).strip()

    section = art.get("articleSection") or []
    if isinstance(section, str):
        section = [section]
    keywords = art.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [keywords]

    image = art.get("thumbnailUrl") or meta(html, "og:image")
    date = art.get("dateModified") or art.get("datePublished")

    return {
        "url": url,
        "title": (title or "").strip(),
        "mapq": mapq,
        "types": [s.strip() for s in section if s and s.strip()],
        "keywords": [k.strip() for k in keywords if k and k.strip()],
        "image": image,
        "date": date,
    }


def main():
    with open(URLS, encoding="utf-8") as f:
        urls = [l.strip() for l in f if l.strip()]

    done = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for rec in json.load(f):
                done[rec["url"]] = rec
    todo = [u for u in urls if u not in done]
    print(f"{len(urls)} total, {len(done)} already scraped, {len(todo)} to do")

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
                results[u] = {"url": u, "title": "", "mapq": None, "types": [],
                              "keywords": [], "image": None, "date": None, "error": str(e)}
            if i % 100 == 0:
                print(f"  {i}/{len(todo)} (errors={errors})")
                with open(OUT, "w", encoding="utf-8") as f:
                    json.dump(list(results.values()), f, ensure_ascii=False)

    out = [results[u] for u in urls if u in results]
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    with_map = sum(1 for r in out if r.get("mapq"))
    print(f"Done. {len(out)} posts, {with_map} with a map place query, {errors} errors -> {OUT}")


if __name__ == "__main__":
    main()
