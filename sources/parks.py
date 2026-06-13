#!/usr/bin/env python3
"""רשות הטבע והגנים (Israel Nature and Parks Authority) source.

Reads sources/cache/parks_raw.json — a dump of the site's WordPress REST API
(https://www.parks.org.il/wp-json/wp/v2/rp, the reserve-park post type; the
site is CloudFront-protected so the dump is fetched in a real browser).
Coordinates are ITM / Israeli TM Grid (EPSG:2039) and are converted to WGS84
here. Emits data/raw/parks.json in the shared schema.
"""
import html
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "cache", "parks_raw.json")
OUT = os.path.join(HERE, "..", "data", "raw", "parks.json")

BASE_TYPE = "שמורות טבע וגנים לאומיים"

# acf filter flag -> (type to add, keyword to add)
FILTER_MAP = {
    "blooming_f": ("טיולי פריחה", None),
    "viewpoint_f": ("נקודות תצפית", None),
    "water_access_f": ("טיולי מים", None),
    "picnic_f": ("פארקים לפיקניק", None),
    "not_paid_f": ("טיולים בחינם", None),
    "caves_f": (None, "מערות"),
    "archaeology_f": (None, "ארכאולוגיה"),
    "accessible_f": (None, "מסלול נגיש"),
}


# ---------- ITM (EPSG:2039) -> WGS84 ----------
# GRS80 ellipsoid + projection constants from epsg.io/2039.
A = 6378137.0
F = 1 / 298.257222101
E2 = F * (2 - F)
E4, E6 = E2 ** 2, E2 ** 3
K0 = 1.0000067
LAT0 = math.radians(31.7343936111111)
LON0 = math.radians(35.2045169444444)
FE, FN = 219529.584, 626907.39


def _meridian_arc(phi):
    return A * ((1 - E2 / 4 - 3 * E4 / 64 - 5 * E6 / 256) * phi
                - (3 * E2 / 8 + 3 * E4 / 32 + 45 * E6 / 1024) * math.sin(2 * phi)
                + (15 * E4 / 256 + 45 * E6 / 1024) * math.sin(4 * phi)
                - (35 * E6 / 3072) * math.sin(6 * phi))


def itm_to_wgs84(x, y):
    m = _meridian_arc(LAT0) + (y - FN) / K0
    mu = m / (A * (1 - E2 / 4 - 3 * E4 / 64 - 5 * E6 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    phi1 = (mu
            + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    sin1, cos1, tan1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    ep2 = E2 / (1 - E2)
    c1 = ep2 * cos1 ** 2
    t1 = tan1 ** 2
    n1 = A / math.sqrt(1 - E2 * sin1 ** 2)
    r1 = A * (1 - E2) / (1 - E2 * sin1 ** 2) ** 1.5
    d = (x - FE) / (n1 * K0)
    lat = phi1 - (n1 * tan1 / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = LON0 + (
        d
        - (1 + 2 * t1 + c1) * d ** 3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / cos1
    return math.degrees(lat), math.degrees(lon)


# ---------- record mapping ----------
TAG = re.compile(r"<[^>]+>")


def strip_html(s):
    return html.unescape(TAG.sub("", s or "")).strip()


def hours_text(h):
    """The API returns separate summer/winter open/close fields; condense."""
    if not isinstance(h, dict):
        return None
    parts = []
    so, sc = h.get("Summer_Opening_Hours_s"), h.get("Summer_Closing_Hours_s")
    wo, wc = h.get("Winter_Opening_Hours_s"), h.get("Winter_Closing_Hours_s")
    if so and sc:
        parts.append(f"קיץ {so}–{sc}")
    if wo and wc:
        parts.append(f"חורף {wo}–{wc}")
    return " · ".join(parts) or None


def main():
    raw = open(RAW, encoding="utf-8").read()
    data = json.loads(raw)
    if isinstance(data, str):  # browser dump may be double-encoded
        data = json.loads(data)

    records, skipped = [], 0
    for x in data:
        if not x.get("itm_x") or not x.get("itm_y"):
            skipped += 1
            continue
        try:
            lat, lng = itm_to_wgs84(float(str(x["itm_x"]).replace(",", "")),
                                    float(str(x["itm_y"]).replace(",", "")))
        except ValueError:
            skipped += 1
            continue
        if not (29.0 <= lat <= 33.5 and 34.0 <= lng <= 36.0):
            skipped += 1
            continue
        flt = x.get("filters") or {}
        types, keywords = [BASE_TYPE], []
        for flag, (t, kw) in FILTER_MAP.items():
            if flt.get(flag):
                if t and t not in types:
                    types.append(t)
                if kw:
                    keywords.append(kw)
        fee = "yes" if flt.get("paid_f") else ("no" if flt.get("not_paid_f") else None)
        records.append({
            "source": "parks",
            "title": html.unescape(x["title"] or "").strip(),
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "region": None,
            "types": types,
            "keywords": keywords,
            "image": x.get("image") or None,
            "url": x["link"],
            "address": None,
            "description": strip_html(x.get("excerpt")) or None,
            "hours": hours_text(x.get("hours")),
            "fee": fee,
        })

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    print(f"Wrote {len(records)} parks ({skipped} without usable coordinates) -> {OUT}")


if __name__ == "__main__":
    main()
