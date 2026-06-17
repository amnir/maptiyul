#!/usr/bin/env python3
"""Build-time enrichment: assign planning `tags` (controlled vocabulary) and an
estimated `duration_min` to every attraction.

This is the offline "labeling" step for the trip planner. The Netanya/Sharon
pilot (~113 places) is hand-curated (LLM-assisted, authoritative); every other
place is rule-derived from types[]/keywords via rule_tags(). The output is
committed as data/enrichment/tags.json and merged into the dataset by build.py.
A future pass can replace the rule fallback with real per-place labels (e.g. a
runtime model) — the schema stays the same.

Output: data/enrichment/tags.json  ->  { "<source url>": {tags, duration_min, title} }

Run:  python3 enrich/tags.py
"""
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ATTRACTIONS = os.path.join(ROOT, "data", "attractions.json")
OUT = os.path.join(ROOT, "data", "enrichment", "tags.json")

# Pilot scope — must match index.html's planner anchor/radius.
ANCHOR = (32.3215, 34.8532)
RADIUS_KM = 12

# Controlled vocabulary. Labels MUST come from this set (asserted below). Grow it
# deliberately — adding a dimension is a vocab entry + a re-label, not a schema change.
VOCAB = {
    "indoor", "outdoor", "kid-friendly", "scenic",
    "rainy-day-ok", "food", "quick-stop", "nature", "beach",
}

# Reusable presets: (tags, duration_min).
COFFEE      = (["outdoor", "food", "quick-stop"], 30)
COFFEE_VIEW = (["outdoor", "food", "quick-stop", "scenic"], 30)
BEACH       = (["outdoor", "beach", "scenic"], 60)
SEA_RESERVE = (["outdoor", "nature", "scenic", "beach"], 60)
NATURE      = (["outdoor", "nature", "scenic"], 60)
NATURE_KID  = (["outdoor", "nature", "scenic", "kid-friendly"], 60)
RESERVE     = (["outdoor", "nature", "scenic"], 45)
MUSEUM      = (["indoor", "rainy-day-ok"], 75)
INDOOR_KID  = (["indoor", "kid-friendly", "rainy-day-ok"], 90)
FARM_KID    = (["outdoor", "kid-friendly"], 75)
PICK_KID    = (["outdoor", "kid-friendly"], 60)
PARAGLIDE   = (["outdoor", "scenic"], 60)

# Per-place labels, in the same order as the deduped pilot set sorted by title.
# Index-aligned with build_pilot(); a length/title mismatch aborts the run.
DEC = [
    COFFEE,                                              # 0  Gaba's
    COFFEE_VIEW,                                         # 1  אָחוּקָפֶה (nahal Alexander)
    (["outdoor", "nature", "scenic", "kid-friendly"], 90),  # 2  אגמון חפר
    NATURE,                                              # 3  אגמון פולג
    INDOOR_KID,                                          # 4  אורבניה מדינת הילדים (משחקייה)
    (["indoor", "kid-friendly", "rainy-day-ok"], 60),   # 5  אלפא סקיי (indoor jump park)
    COFFEE,                                              # 6  אלפרד
    COFFEE,                                              # 7  אריקפה
    (["indoor", "kid-friendly", "rainy-day-ok"], 75),   # 8  ארץ עוץ
    COFFEE,                                              # 9  אשרק'ה
    COFFEE,                                              # 10 בוגיס
    (["indoor", "rainy-day-ok"], 60),                   # 11 בית הראשונים עמק חפר
    MUSEUM,                                              # 12 בית טרזין (Holocaust museum)
    (["outdoor"], 90),                                  # 13 בית ספר לצלילה לי ים (diving)
    COFFEE,                                              # 14 ברוש - עגלה במושבה
    COFFEE_VIEW,                                         # 15 בריזה (cart at viewpoint)
    INDOOR_KID,                                          # 16 ג'ימבו פליי (trampolines)
    INDOOR_KID,                                          # 17 ג'ימבולנד
    NATURE,                                              # 18 גבעת האלון
    (["outdoor", "kid-friendly"], 60),                  # 19 גו קארטינג נתניה
    NATURE,                                              # 20 גן בוטני
    (["outdoor", "beach", "scenic"], 90),               # 21 גן לאומי חוף בית ינאי
    (["outdoor", "nature", "scenic"], 90),              # 22 גן לאומי חוף השרון שביל המצוק
    (["outdoor", "nature", "scenic", "beach"], 90),     # 23 גן לאומי נחל אלכסנדר – חוף בית ינאי
    (["outdoor", "nature", "scenic"], 75),              # 24 גן לאומי נחל אלכסנדר – חורבת סמרה
    NATURE_KID,                                          # 25 גשר הצבים – פארק צבי הנחל
    PARAGLIDE,                                           # 26 דביר מצנחי רחיפה
    FARM_KID,                                            # 27 החווה בחבצלת השרון
    INDOOR_KID,                                          # 28 החלל המופלא
    PARAGLIDE,                                           # 29 המרכז הישראלי לרחיפה
    COFFEE,                                              # 30 העגלה של גילי
    NATURE,                                              # 31 חוות הנוי (botanical)
    (["outdoor", "kid-friendly"], 60),                  # 32 חוות הסוסים בביתן אהרון
    (["outdoor", "kid-friendly"], 60),                  # 33 חוות התוכים בכפר הס
    BEACH,                                               # 34 חוף מכמורת
    BEACH,                                               # 35 חוף סירונית
    BEACH,                                               # 36 חוף פולג
    (["outdoor", "nature", "scenic"], 90),              # 37 חופי השרון – מסלול ג'יפים
    NATURE_KID,                                          # 38 חורשת הסרג'נטים – יער נתניה
    (["outdoor", "nature"], 60),                        # 39 חניון הכוכבים (camping)
    COFFEE,                                              # 40 חרותא
    (["outdoor", "scenic", "quick-stop"], 45),          # 41 טיילות נתניה (promenade)
    NATURE,                                              # 42 יער האילנות ליד קדימה
    NATURE_KID,                                          # 43 יער האילנות מערב
    (["outdoor", "nature", "scenic"], 75),              # 44 יער האילנות – ארבורטום ומרכז מבקרים
    NATURE_KID,                                          # 45 יער קדימה
    (["indoor", "food"], 75),                           # 46 יקב אלכסנדר (winery)
    COFFEE,                                              # 47 לוקה Luka
    PARAGLIDE,                                           # 48 לטוס – שגב ברעם
    COFFEE,                                              # 49 לילו קפה
    (["outdoor", "nature", "scenic"], 45),              # 50 מאגר משמר השרון – מצפור
    (["outdoor", "kid-friendly"], 60),                  # 51 מדוושי ישראל
    MUSEUM,                                              # 52 מוזיאון בית הגדודים
    (["indoor", "kid-friendly", "rainy-day-ok"], 75),   # 53 מוזיאון הטרקטור בעין ורד
    (["outdoor", "kid-friendly"], 60),                  # 54 מכוורת יום בכפר (bees)
    COFFEE,                                              # 55 מלוו - mellow
    (["outdoor", "kid-friendly", "scenic"], 60),        # 56 מרכז ההצלה של צבי הים
    (["indoor", "food", "kid-friendly", "rainy-day-ok"], 60),  # 57 מרכז המבקרים רולדין
    (["indoor", "rainy-day-ok"], 60),                   # 58 מרכז המבקרים סיקורה
    FARM_KID,                                            # 59 משק ברגר
    FARM_KID,                                            # 60 משק הכוכבים
    NATURE,                                              # 61 נחל אלכסנדר
    NATURE,                                              # 62 נחל פולג – דיונות וינגייט
    (["outdoor", "kid-friendly"], 60),                  # 63 סוס ועגלה
    COFFEE,                                              # 64 עגלאטה
    COFFEE,                                              # 65 עגלה של קפה
    COFFEE,                                              # 66 עגלה של קפה בית הראשונים
    COFFEE,                                              # 67 עגלת קפה
    COFFEE,                                              # 68 עגלת קפה בגינת אוכל משק הלברכט
    COFFEE,                                              # 69 עגלת קפה הפוכות
    COFFEE,                                              # 70 עגלת קפה לוקה קפה בשדה
    COFFEE,                                              # 71 עגלתא
    NATURE,                                              # 72 פארק בריכת החורף לב השרון
    (["outdoor", "nature", "kid-friendly"], 45),        # 73 פארק שלולית החורף – בריכת דורה
    COFFEE,                                              # 74 פוזה לקפה
    COFFEE,                                              # 75 פוזלה
    COFFEE,                                              # 76 פזי קפה
    COFFEE,                                              # 77 פזיקפה
    COFFEE,                                              # 78 פטיט קפה
    INDOOR_KID,                                          # 79 פלנתניה – מרכז חלל, מדע ותרבות יפן
    INDOOR_KID,                                          # 80 פלנתניה – מרכז מדע, חלל ותרבות יפן
    (["indoor", "kid-friendly", "rainy-day-ok"], 75),   # 81 פעלולים
    COFFEE,                                              # 82 צ'ופצ'יק
    COFFEE,                                              # 83 קופילה
    PICK_KID,                                            # 84 קטיף עצמי בכפר נטר
    PICK_KID,                                            # 85 קטיף עצמי פטל
    (["outdoor", "nature", "scenic"], 90),              # 86 קטע מספר 15 – מחוף פולג
    NATURE_KID,                                          # 87 קטע נחל לדוגמא – פארק איטליה
    (["indoor", "kid-friendly", "rainy-day-ok"], 60),   # 88 קיר טיפוס העוגן (climbing)
    COFFEE,                                              # 89 קפה ארטורה
    COFFEE,                                              # 90 קפה בבקי
    COFFEE,                                              # 91 קפה בפטל
    COFFEE,                                              # 92 קפה גדליה
    COFFEE,                                              # 93 קפה ליברל
    COFFEE,                                              # 94 קפה ממרא
    COFFEE,                                              # 95 קפה ממש
    COFFEE,                                              # 96 קפה נוגה
    COFFEE,                                              # 97 קפה רוסו
    COFFEE,                                              # 98 שולקה
    (["indoor", "kid-friendly", "rainy-day-ok"], 75),   # 99 שחק אותה
    RESERVE,                                             # 100 שמורת אירוס הארגמן בנתניה
    RESERVE,                                             # 101 שמורת ביתן אהרון
    NATURE,                                              # 102 שמורת בריכת היער עטא
    RESERVE,                                             # 103 שמורת הטבע אודים (פריחה)
    RESERVE,                                             # 104 שמורת הטבע בני ציון
    RESERVE,                                             # 105 שמורת הטבע קדימה
    NATURE,                                              # 106 שמורת ויער קדימה
    RESERVE,                                             # 107 שמורת טבע אודים
    NATURE,                                              # 108 שמורת טבע נחל פולג
    SEA_RESERVE,                                         # 109 שמורת טבע צוקי ים
    SEA_RESERVE,                                         # 110 שמורת ים גדור
    NATURE,                                              # 111 שמורת יקום
    PICK_KID,                                            # 112 תות בקיבוץ (קטיף)
]


def hav_km(a, b):
    R = 6371
    r = math.radians
    dlat, dlng = r(b[0] - a[0]), r(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(r(a[0])) * math.cos(r(b[0])) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def richness(a):
    return (2 if a.get("image") else 0) + (1 if a.get("description") else 0) + (1 if a.get("address") else 0)


def build_pilot(arr):
    """Reproduce the planner's pilot set: within RADIUS_KM of ANCHOR, deduped by
    ~110 m coord buckets (richest wins), sorted by title — same as index.html."""
    cands = [a for a in arr if a.get("lat") and a.get("lng")
             and hav_km(ANCHOR, (a["lat"], a["lng"])) <= RADIUS_KM]
    by = {}
    for a in cands:
        k = f"{a['lat']:.3f},{a['lng']:.3f}"
        if k not in by or richness(a) > richness(by[k]):
            by[k] = a
    return sorted(by.values(), key=lambda a: a["title"])


# ---------- rule-based fallback (for places outside the curated pilot) ----------
COFFEE_TYPE = "עגלות קפה ופוד טראק"
MUSEUM_TYPE = "מוזיאון, אתר מורשת, מרכז מבקרים ועתיקות"
NATURE_TYPES = ["טיולי פריחה", "נקודות עניין בטבע", "שמורות טבע וגנים לאומיים",
                "נקודות תצפית", "פארקים לפיקניק", "מסלולי טיול"]
KIDS_TYPES = ["פארק שעשועים", "טיולים עם עגלות", "טיולים עם חיות"]

# Indoor detector — encodes the per-name judgment from the pilot so it generalises
# nationwide (the old JS regex was far narrower and missed e.g. "מרכז המבקרים").
INDOOR_RE = re.compile(
    r"מוזיאון|מרכז מדע|מדע וטכנולוגיה|מרכז מבקרים|מרכז המבקרים|משחקיי|משחקיה|"
    r"אסקייפ|escape|חדר בריחה|חדרי בריחה|טרמפולינ|ג'ימבו|ג׳ימבו|באולינג|"
    r"פלנטריום|פלנת|גלריה|לייזר|נינג'ה|נינג׳ה|אקווריום|מצפה כוכבים|"
    r"חלל המופלא|אורבניה|בית הראשונים|יקב|קיר טיפוס|תיאטרון|סינמה|קולנוע")
KIDS_RE = re.compile(r"טרמפולינ|ג'ימבו|ג׳ימבו|משחקיי|משחקיה|ילדים|משפח|שעשוע")
BEACH_RE = re.compile(r"חוף|טיילת")


def rule_tags(a):
    """Derive (tags, duration_min) from types[]/keywords for a non-pilot place."""
    types = a.get("types", [])
    hay = (a.get("title", "") + " " + " ".join(a.get("keywords", [])) + " " + " ".join(types))
    tags = set()
    is_coffee = COFFEE_TYPE in types
    is_indoor = MUSEUM_TYPE in types or bool(INDOOR_RE.search(hay))
    is_beach = "טיולי מים" in types or bool(BEACH_RE.search(hay))
    is_nature = any(t in types for t in NATURE_TYPES)
    is_kids = any(t in types for t in KIDS_TYPES) or bool(KIDS_RE.search(hay))

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
    # Plain attraction with no spatial signal → assume outdoor (coarse default).
    if not is_indoor and not (tags & {"outdoor", "beach", "nature"}):
        tags.add("outdoor")
    # indoor wins any accidental outdoor/beach co-tag
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


def main():
    arr = json.load(open(ATTRACTIONS, encoding="utf-8"))
    pilot = build_pilot(arr)
    if len(pilot) != len(DEC):
        raise SystemExit(f"Pilot set is {len(pilot)} places but DEC has {len(DEC)} labels — "
                         f"data changed; re-align enrich/tags.py before committing.")

    # Curated pilot labels are authoritative; everything else is rule-derived.
    curated = {}
    for place, (tags, dur) in zip(pilot, DEC):
        bad = set(tags) - VOCAB
        if bad:
            raise SystemExit(f"Out-of-vocabulary tag(s) {bad} on {place['title']!r}")
        curated[place["sources"][0]["url"]] = (tags, dur)

    out, n_rule = {}, 0
    for a in arr:
        if not a.get("sources"):
            continue
        url = a["sources"][0]["url"]
        if url in curated:
            tags, dur = curated[url]
        else:
            tags, dur = rule_tags(a)
            n_rule += 1
        if tags:
            out[url] = {"tags": tags, "duration_min": dur, "title": a["title"]}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    indoor = sum(1 for v in out.values() if "indoor" in v["tags"])
    print(f"Wrote {len(out)} labels ({len(curated)} curated pilot, {n_rule} rule-based) -> {OUT}")
    print(f"  indoor: {indoor} | outdoor: {sum(1 for v in out.values() if 'outdoor' in v['tags'])}")


if __name__ == "__main__":
    main()
