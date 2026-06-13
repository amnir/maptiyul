#!/usr/bin/env python3
"""Download named OSM POIs covering Israel from the Overpass API.

One bulk query (not per-place) per the public instance's fair-use policy.
Output: data/enrichment/osm_pois.json — a flat list of
  {name, lat, lng, tags: {opening_hours, phone, website, wheelchair, fee, ...}}
build.py matches these to map places by proximity + fuzzy name and copies the
useful tags onto each place.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "enrichment", "osm_pois.json")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Bounding box covering Israel incl. Golan and the West Bank (south,west,north,east).
BBOX = "29.4,34.2,33.4,35.95"

# Only named POIs — unnamed ones can never match a place by name.
QUERY = f"""
[out:json][timeout:600][bbox:{BBOX}];
(
  nwr["name"]["tourism"~"^(attraction|museum|viewpoint|picnic_site|zoo|theme_park|camp_site|aquarium)$"];
  nwr["name"]["leisure"~"^(park|nature_reserve|garden|water_park)$"];
  nwr["name"]["boundary"="national_park"];
  nwr["name"]["amenity"~"^(cafe|fast_food)$"];
  nwr["name"]["natural"="spring"];
  nwr["name"]["historic"~"^(archaeological_site|ruins|castle|fort|memorial)$"];
);
out center tags;
"""

# Tags worth carrying over to the map.
KEEP_TAGS = [
    "opening_hours", "phone", "contact:phone", "website", "contact:website",
    "wheelchair", "fee", "name", "name:he", "name:en",
]


def main():
    print("Querying Overpass (single bulk request, may take a few minutes)...")
    req = urllib.request.Request(
        OVERPASS_URL,
        data=urllib.parse.urlencode({"data": QUERY}).encode(),
        headers={"User-Agent": "attractions-map-enrichment/1.0"},
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        data = json.load(resp)

    pois = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "node":
            lat, lng = el.get("lat"), el.get("lon")
        else:
            center = el.get("center") or {}
            lat, lng = center.get("lat"), center.get("lon")
        if lat is None or lng is None:
            continue
        kept = {k: v for k, v in tags.items() if k in KEEP_TAGS}
        # Skip POIs with a name but none of the enrichment fields (KEEP_TAGS[7:]
        # are name variants, which every queried POI has — exclude them here).
        if not any(k in kept for k in KEEP_TAGS[:7]):
            continue
        pois.append({
            "name": tags.get("name:he") or tags["name"],
            "names": [n for n in {tags.get("name"), tags.get("name:he"), tags.get("name:en")} if n],
            "lat": lat,
            "lng": lng,
            "tags": kept,
        })

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(pois, f, ensure_ascii=False)
    print(f"Wrote {len(pois)} named POIs with enrichment tags -> {OUT}")


if __name__ == "__main__":
    main()
