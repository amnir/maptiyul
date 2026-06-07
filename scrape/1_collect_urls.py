#!/usr/bin/env python3
"""Collect every post URL from the Yoast post sitemaps into data/urls.txt."""
import os
import re
import urllib.request

SITEMAPS = [
    "https://familytrips.co.il/post-sitemap.xml",
    "https://familytrips.co.il/post-sitemap2.xml",
    "https://familytrips.co.il/post-sitemap3.xml",
]
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "urls.txt")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (attractions-map builder)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def main():
    urls = []
    for sm in SITEMAPS:
        xml = fetch(sm)
        found = re.findall(r"<loc>([^<]+)</loc>", xml)
        print(f"{sm}: {len(found)} urls")
        urls.extend(found)
    # dedupe, keep order
    seen, uniq = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(uniq) + "\n")
    print(f"Total unique: {len(uniq)} -> {OUT}")


if __name__ == "__main__":
    main()
