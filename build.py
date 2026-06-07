#!/usr/bin/env python3
"""Merge every source in data/raw/ into the final map dataset, de-duplicating
places that appear in more than one source.

Inputs : data/raw/*.json   (records in the shared schema; see README)
Outputs: data/attractions.json  and  data/attractions.js  (used by index.html)
"""
import glob
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "data", "raw")
OUT_JSON = os.path.join(HERE, "data", "attractions.json")
OUT_JS = os.path.join(HERE, "data", "attractions.js")

SOURCE_LABELS = {
    "familytrips": "בשביל המשפחה",
    "coffeetrail": "Coffee Trail",
}
COFFEE_TYPE = "עגלות קפה ופוד טראק"

# Leading descriptor words to drop when comparing names across sources.
NAME_PREFIXES = [
    "גן לאומי", "הגן הלאומי", "שמורת הטבע", "שמורת טבע", "פארק לאומי",
    "עגלת קפה", "עגלת הקפה", "פוד טראק", "פודטראק", "קפה",
]


# ---------- geometry ----------
def haversine_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def region_from_coords(lat, lng):
    if 31.70 <= lat <= 31.85 and 35.13 <= lng <= 35.27:
        return "ירושלים"
    if lat >= 32.5:
        return "צפון"
    if lat >= 31.5:
        return "מרכז"
    return "דרום"


# ---------- name matching ----------
NIQQUD = re.compile(r"[֑-ׇ]")


def norm_name(s):
    s = NIQQUD.sub("", s or "")
    s = re.sub(r"[\"'`׳״.,()|\-–—]", " ", s)
    s = s.lower().strip()
    for p in NAME_PREFIXES:
        if s.startswith(p + " "):
            s = s[len(p):].strip()
    return re.sub(r"\s+", " ", s)


def name_match(n1, n2):
    a, b = norm_name(n1), norm_name(n2)
    if not a or not b:
        return 0.0
    shorter = min(a, b, key=len)
    if len(shorter) >= 4 and (a in b or b in a):
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def same_place(r1, r2):
    # Only de-dup across different sources. Two entries from the same source are
    # distinct listings; and familytrips names are often geocoded to a shared
    # town centroid, so distance alone is not a reliable signal there.
    if r1["source"] == r2["source"]:
        return False
    d = haversine_m((r1["lat"], r1["lng"]), (r2["lat"], r2["lng"]))
    sim = name_match(r1["title"], r2["title"])
    if d <= 200 and sim >= 0.55:
        return True                      # co-located + similar name
    both_coffee = COFFEE_TYPE in r1["types"] and COFFEE_TYPE in r2["types"]
    if both_coffee and d <= 600 and sim >= 0.75:
        return True                      # same cart, loose geocoding (not a different branch)
    return False


# ---------- union-find ----------
def cluster(records):
    parent = list(range(len(records)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Bucket by ~5km grid (scanning neighbours covers the widest match range).
    buckets = {}
    for i, r in enumerate(records):
        key = (round(r["lat"] / 0.05), round(r["lng"] / 0.05))
        buckets.setdefault(key, []).append(i)

    for (gx, gy), idxs in buckets.items():
        neighbours = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neighbours += buckets.get((gx + dx, gy + dy), [])
        for i in idxs:
            for j in neighbours:
                if j > i and same_place(records[i], records[j]):
                    union(i, j)

    groups = {}
    for i in range(len(records)):
        groups.setdefault(find(i), []).append(records[i])
    return list(groups.values())


# ---------- merge ----------
def merge_group(members):
    # Prefer a member with an explicit address (Coffee Trail has exact coords).
    primary = next((m for m in members if m.get("address")), members[0])

    types, kw, sources = [], [], []
    seen_src = set()
    image = description = None
    region = None
    for m in members:
        for t in m.get("types", []):
            if t not in types:
                types.append(t)
        for k in m.get("keywords", []):
            if k not in kw:
                kw.append(k)
        key = (m["source"], m["url"])
        if key not in seen_src:
            seen_src.add(key)
            sources.append({"name": m["source"], "label": SOURCE_LABELS.get(m["source"], m["source"]), "url": m["url"]})
        image = image or m.get("image")
        description = description or m.get("description")
        region = region or m.get("region")

    return {
        "title": primary["title"],
        "lat": primary["lat"],
        "lng": primary["lng"],
        "region": region or region_from_coords(primary["lat"], primary["lng"]),
        "types": types,
        "keywords": kw,
        "image": image,
        "address": primary.get("address"),
        "description": description,
        "sources": sources,
    }


def main():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.json")))
    records = []
    per_source = {}
    for fp in files:
        data = json.load(open(fp, encoding="utf-8"))
        kept = [r for r in data if r.get("lat") and r.get("lng")]
        per_source[os.path.basename(fp)] = (len(data), len(kept))
        records.extend(kept)

    print("Sources:")
    for name, (total, kept) in per_source.items():
        print(f"  {name}: {kept}/{total} with coordinates")
    print(f"Total input points: {len(records)}")

    groups = cluster(records)
    merged = [merge_group(g) for g in groups]
    multi = sum(1 for g in groups if len({(m['source']) for m in g}) > 1)
    print(f"After de-dup: {len(merged)} places "
          f"({len(records) - len(merged)} merged away, {multi} span multiple sources)")

    merged.sort(key=lambda x: x["title"])
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False)
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("window.ATTRACTIONS = ")
        json.dump(merged, f, ensure_ascii=False)
        f.write(";\n")
    print(f"Wrote {len(merged)} places -> {OUT_JSON} and {OUT_JS}")


if __name__ == "__main__":
    main()
