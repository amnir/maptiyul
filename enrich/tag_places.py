#!/usr/bin/env python3
"""Fill planning `tags` + `duration_min` for any attraction missing them, writing
directly into data/attractions.json (the canonical state) and regenerating
data/attractions.js. Existing tags are never touched.

This is the engine behind the `tag-places` skill. tags[] use a controlled
vocabulary (VOCAB); duration_min is the planner's per-stop scheduling estimate.

Usage:
  python3 enrich/tag_places.py --list   # report places missing tags
  python3 enrich/tag_places.py          # fill missing tags + rewrite .json/.js
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JSON_FP = os.path.join(ROOT, "data", "attractions.json")
JS_FP = os.path.join(ROOT, "data", "attractions.js")

# Controlled vocabulary — grow deliberately (a new dimension is a vocab entry).
VOCAB = {
    "indoor", "outdoor", "kid-friendly", "scenic",
    "rainy-day-ok", "food", "quick-stop", "nature", "beach",
}

COFFEE_TYPE = "עגלות קפה ופוד טראק"
MUSEUM_TYPE = "מוזיאון, אתר מורשת, מרכז מבקרים ועתיקות"
KIDSFUN_TYPE = "משחקיות ובילוי מקורה"  # sources/kidsfun.py curated venues
NATURE_TYPES = ["טיולי פריחה", "נקודות עניין בטבע", "שמורות טבע וגנים לאומיים",
                "נקודות תצפית", "פארקים לפיקניק", "מסלולי טיול"]
KIDS_TYPES = ["פארק שעשועים", "טיולים עם עגלות", "טיולים עם חיות"]

INDOOR_RE = re.compile(
    r"מוזיאון|מרכז מדע|מדע וטכנולוגיה|מרכז מבקרים|מרכז המבקרים|משחקיי|משחקיה|"
    r"אסקייפ|escape|חדר בריחה|חדרי בריחה|טרמפולינ|ג'ימבו|ג׳ימבו|באולינג|"
    r"פלנטריום|פלנת|גלריה|לייזר|נינג'ה|נינג׳ה|אקווריום|מצפה כוכבים|"
    r"חלל המופלא|אורבניה|בית הראשונים|יקב|קיר טיפוס|תיאטרון|סינמה|קולנוע|"
    r"פעלטון|לונדע|סופט פליי|ג'ימבורי|ג׳ימבורי")
KIDS_RE = re.compile(r"טרמפולינ|ג'ימבו|ג׳ימבו|משחקיי|משחקיה|ילדים|משפח|שעשוע|פעלטון|לונדע")
BEACH_RE = re.compile(r"חוף|טיילת")


def rule_tags(a):
    """Derive (tags, duration_min) from types[]/keywords. Coarse but consistent;
    hand-correct ambiguous cases by editing attractions.json directly."""
    types = a.get("types", [])
    hay = (a.get("title", "") + " " + " ".join(a.get("keywords", [])) + " " + " ".join(types))
    tags = set()
    is_coffee = COFFEE_TYPE in types
    is_indoor = MUSEUM_TYPE in types or KIDSFUN_TYPE in types or bool(INDOOR_RE.search(hay))
    is_beach = "טיולי מים" in types or bool(BEACH_RE.search(hay))
    is_nature = any(t in types for t in NATURE_TYPES)
    is_kids = any(t in types for t in KIDS_TYPES) or KIDSFUN_TYPE in types or bool(KIDS_RE.search(hay))

    if is_coffee:
        tags |= {"outdoor", "food", "quick-stop"}
    if is_indoor:
        tags |= {"indoor", "rainy-day-ok"}
    if is_beach and not is_indoor:
        tags |= {"outdoor", "beach", "scenic"}
    if is_nature and not is_indoor:
        tags |= {"outdoor", "nature", "scenic"}
    if "נקודות תצפית" in types:
        tags |= {"outdoor", "scenic"}
    if is_kids:
        tags.add("kid-friendly")
    if not is_indoor and not (tags & {"outdoor", "beach", "nature"}):
        tags.add("outdoor")  # plain attraction with no spatial signal → assume outdoor
    if is_indoor:
        tags -= {"outdoor", "beach"}

    if is_coffee:
        dur = 30
    elif is_indoor:
        dur = 90 if "kid-friendly" in tags else 75
    elif is_beach:
        dur = 60
    elif is_kids:
        dur = 75
    elif "מסלולי טיול" in types:
        dur = 90
    else:
        dur = 60
    return sorted(tags & VOCAB), dur


def write(arr):
    with open(JSON_FP, "w", encoding="utf-8") as f:
        json.dump(arr, f, ensure_ascii=False)
    with open(JS_FP, "w", encoding="utf-8") as f:
        f.write("window.ATTRACTIONS = ")
        json.dump(arr, f, ensure_ascii=False)
        f.write(";\n")


def main():
    arr = json.load(open(JSON_FP, encoding="utf-8"))
    missing = [a for a in arr if not a.get("tags")]

    if "--list" in sys.argv:
        print(f"{len(missing)} / {len(arr)} places missing tags")
        for a in missing[:50]:
            print("  ", a.get("title", "?"))
        return

    n = 0
    for a in missing:
        tags, dur = rule_tags(a)
        if tags:
            a["tags"] = tags
            a["duration_min"] = dur
            n += 1
    write(arr)
    print(f"Tagged {n} previously-untagged places ({len(missing) - n} left empty); "
          f"rewrote attractions.json + attractions.js")


if __name__ == "__main__":
    main()
