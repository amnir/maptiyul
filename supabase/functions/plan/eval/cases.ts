// Gold test cases — one per "route type". The intent fields (area/origin/prefs)
// and rubric (maxRouteKm/stopCountTol) are authored by hand; `stops` is the ideal
// itinerary picked from the SAME deterministic candidate pool the agent sees,
// dumped offline with `dump.ts --case <id>` so every title is a real dataset title.
//
// Re-author after the dataset changes: `deno run --allow-net eval/dump.ts --case <id>`
// then update `stops`.

import type { GoldCase } from "./score.ts";

export const CASES: GoldCase[] = [
  {
    id: "coastal-sharon-halfday",
    routeType: "coastal / beach + coffee, half day, with origin",
    query: "אני מתל אביב, בא לי חצי יום של חוף, טיילת וכוס קפה טובה באזור השרון",
    duration: "half",
    origin: { lat: 32.08, lng: 34.78 }, // Tel Aviv
    area: { name: "השרון", lat: 32.32, lng: 34.85, radiusKm: 20 },
    prefs: ["beach", "coffee"],
    stops: [
      { title: "חוף פולג", cat: "beach" },
      { title: "שמורת טבע צוקי ים", cat: "nature" },
      { title: "טיילות נתניה", cat: "attraction" },
      { title: "קפה נוגה", cat: "coffee" },
    ],
    maxRouteKm: 45,
    notes: "TLV origin → route should run roughly south→north up the Sharon coast.",
  },
  {
    id: "family-galilee-fullday",
    routeType: "family / kids, full day, no origin",
    query: "טיול משפחתי של יום שלם עם ילדים קטנים בגליל, משהו כיף שהם יאהבו",
    duration: "full",
    origin: null,
    area: { name: "הגליל", lat: 32.92, lng: 35.30, radiusKm: 25 },
    prefs: ["kids"],
    stops: [
      { title: "פארק המשפחה בכרמיאל: המקום המושלם לבילוי עם הילדים", cat: "kids" },
      { title: "פארק המחצבה פארק הגליל בכרמיאל", cat: "nature" },
      { title: "חירבת קב ופארק רבין בכרמיאל: אתר עתיקות בלב פארק ירוק למשפחות", cat: "indoor" },
      { title: "באולינג כרמיאל", cat: "indoor" },
      { title: "שביל סובב כרמיאל: המדריך המלא למסלול ונקודות עניין", cat: "nature" },
      { title: "קפה סמדר", cat: "coffee" },
    ],
    maxRouteKm: 80,
    notes: "Spread-out region; kids-friendly variety over a full day.",
  },
  {
    id: "urban-tlv-indoor-halfday",
    routeType: "urban / rainy-day indoor, half day",
    query: "יום גשום בתל אביב, בא לי משהו מקורה - מוזיאונים או מרכזי מדע",
    duration: "half",
    origin: null,
    area: { name: "תל אביב", lat: 32.08, lng: 34.78, radiusKm: 9 },
    prefs: ["indoor"],
    stops: [
      { title: "מוזיאון תל אביב לאמנות", cat: "indoor" },
      { title: 'מוזיאון האצ"ל', cat: "indoor" },
      { title: "מתחם שרונה: אתר המורשת המפתיע ומנהרות הטמפלרים", cat: "indoor" },
      { title: "מצפה עזריאלי", cat: "attraction" },
    ],
    maxRouteKm: 25,
  },
  {
    id: "nature-carmel-halfday",
    routeType: "nature, half day",
    query: "בא לי טיול טבע יפה בכרמל לחצי יום, נופים ומסלולים",
    duration: "half",
    origin: null,
    area: { name: "הכרמל", lat: 32.73, lng: 35.03, radiusKm: 18 },
    prefs: ["nature"],
    stops: [
      { title: "פארק הכרמל", cat: "nature" },
      { title: "שוויצריה הקטנה: נחל כלח ונחל גלים", cat: "nature" },
      { title: "עין אלון – מעיין הנובע בתוך ערוץ נחל אורן", cat: "nature" },
      { title: "נחל אורן", cat: "nature" },
    ],
    maxRouteKm: 50,
  },
  {
    id: "free-jerusalem-halfday",
    routeType: "free / budget, half day",
    query: "אנחנו בירושלים ומחפשים טיול בחינם לחצי יום, בלי לשלם כניסה",
    duration: "half",
    origin: null,
    area: { name: "ירושלים", lat: 31.78, lng: 35.21, radiusKm: 12 },
    prefs: ["free"],
    stops: [
      { title: "גן הוורדים בירושלים – גן וואהל", cat: "nature" },
      { title: "פארק טדי – מופעי מזרקות המים בירושלים", cat: "kids" },
      { title: "גן לאומי סביב חומות ירושלים העתיקה", cat: "nature" },
      { title: "עין כרם – טיול בסמטאות השכונה הציורית של ירושלים", cat: "indoor" },
    ],
    maxRouteKm: 30,
  },
  {
    id: "kinneret-fullday",
    routeType: "single sub-region anchor, full day, with origin",
    query: "אני מחיפה, רוצה יום שלם של טיול סביב הכנרת עם נופים וקצת אטרקציות",
    duration: "full",
    origin: { lat: 32.82, lng: 34.99 }, // Haifa (north-west of the lake)
    area: { name: "הכנרת", lat: 32.79, lng: 35.55, radiusKm: 18 },
    prefs: ["nature", "attraction"],
    stops: [
      { title: "גן לאומי ושמורת טבע הארבל – מסלולים, תצפיות ונוף הכנרת", cat: "nature" },
      { title: "מרכז מבקרים מגדלא – העיר העתיקה והכנסייה שעל שפת הכנרת", cat: "indoor" },
      { title: "סימבה בכנרת: מתחם אטרקציות לכל המשפחה", cat: "attraction" },
      { title: "חוף גיא – פארק מים על חוף הכנרת", cat: "beach" },
      { title: "גן לאומי חמת טבריה – מעיינות חמים", cat: "attraction" },
      { title: "קפה נומה", cat: "coffee" },
    ],
    maxRouteKm: 90,
    notes: "Haifa origin is north-west of the lake; entry from the north side.",
  },
  {
    // Reproduces a real UI failure: this full-day Eilat+kids request returned no
    // plan in the local UI. Eilat is data-rich (60+ candidates), so it's a latency
    // case, not a coverage one — a full-day (6-stop) two-call run is the slowest
    // shape and can brush the 45s client timeout. Keep it to watch per-model speed.
    id: "eilat-kids-fullday",
    routeType: "far-south / kids, full day (latency stress)",
    query: "תתכנן לי יום שלם באילת עם הילדים",
    duration: "full",
    origin: null,
    area: { name: "אילת", lat: 29.55, lng: 34.95, radiusKm: 20 },
    prefs: ["kids"],
    stops: [
      { title: "פארק הצפרות ובריכות הפלמנגו באילת", cat: "kids" },
      { title: "הגן הבוטני אילת", cat: "nature" },
      { title: "ארץ החרדונים אילת", cat: "kids" },
      { title: "פארק המים יו ספלאש אילת", cat: "beach" },
      { title: "מוזיאון העיר אילת – אילת עירי", cat: "indoor" },
      { title: "מצפור הים האדום אילת", cat: "attraction" },
    ],
    maxRouteKm: 60,
    notes: "Latency stress test — watch the per-call timing vs the 45s client cutoff.",
  },
];

export const byId = (id: string): GoldCase | undefined => CASES.find((c) => c.id === id);
