// Vendor-agnostic LLM trip-planner agent (Supabase Edge Function, Deno).
//
// The function owns the dataset and a two-step pipeline:
//   A) parse the free-text request -> { origin, area, duration, prefs } using the
//      model's own knowledge of Israeli geography for coordinates.
//   B) select & order stops from area-filtered candidates + write Hebrew copy.
// Geometry is deterministic: candidates are filtered to the area, and the chosen
// stops are ordered by projection onto the origin->area axis (so a trip starting
// south of the area runs south->north, and vice-versa). The model handles
// understanding, selection, and copy; it never sees coordinates it can hallucinate
// into the route (stops are resolved back to real pins by index).
//
// Returns directionally-ordered REAL stops; the client computes times/legs/emoji
// and renders. Env (secrets only): LLM_BASE_URL (/v1 root), LLM_API_KEY, LLM_MODEL.
// Dataset is fetched (warm-cached) from the published site — no DB, no secrets here.

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const CATS = ["coffee", "indoor", "beach", "nature", "kids", "attraction"];
const PREF_TOKENS = [...CATS, "free"];
const DATA_URL = "https://amnir.github.io/maptiyul/data/attractions.json";

type Place = {
  title: string; lat: number; lng: number;
  types?: string[]; tags?: string[]; keywords?: string[];
  fee?: string; image?: string; description?: string; address?: string; duration_min?: number;
  _cats?: string[];
};
type LatLng = { lat: number; lng: number };

// ---- dataset (warm in-memory cache) ----------------------------------------
let DATA: Place[] | null = null;
let DATA_AT = 0;
async function getData(): Promise<Place[]> {
  if (DATA && Date.now() - DATA_AT < 3_600_000) return DATA;
  const r = await fetch(DATA_URL);
  if (!r.ok) throw new Error("dataset fetch " + r.status);
  const j = await r.json();
  DATA = (Array.isArray(j) ? j : []).filter((a: any) => a && a.lat && a.lng);
  DATA_AT = Date.now();
  return DATA!;
}

// ---- geo + classify (ported from index.html, kept in sync) -----------------
function hav(a: LatLng, b: LatLng): number {
  const R = 6371, r = (d: number) => d * Math.PI / 180;
  const dLat = r(b.lat - a.lat), dLng = r(b.lng - a.lng);
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(r(a.lat)) * Math.cos(r(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}
const richness = (a: Place) => (a.image ? 2 : 0) + (a.description ? 1 : 0) + (a.address ? 1 : 0);
function dedupe(arr: Place[]): Place[] {
  const by: Record<string, Place> = {};
  for (const a of arr) {
    const k = a.lat.toFixed(3) + "," + a.lng.toFixed(3);
    if (!by[k] || richness(a) > richness(by[k])) by[k] = a;
  }
  return Object.values(by);
}
const isFree = (a: Place) => (a.types || []).includes("טיולים בחינם") || a.fee === "no";
function classify(a: Place): string[] {
  const types = a.types || [];
  const cats: string[] = [];
  if (types.includes("עגלות קפה ופוד טראק")) cats.push("coffee");
  if (types.includes("אטרקציות")) cats.push("attraction");
  const tags = a.tags;
  if (tags && tags.length) {
    if (tags.includes("indoor")) cats.push("indoor");
    if (tags.includes("beach")) cats.push("beach");
    if (tags.includes("nature")) cats.push("nature");
    if (tags.includes("kid-friendly")) cats.push("kids");
  } else {
    const hay = (a.title || "") + " " + (a.keywords || []).join(" ") + " " + types.join(" ");
    if (/מוזיאון|מרכז מדע|מדע|משחקייה|אסקייפ|גלריה|מרכז מבקרים|פלנת|חלל המופלא|אורבניה/.test(hay)) cats.push("indoor");
    if (types.includes("טיולי מים") || /חוף|טיילת/.test(hay)) cats.push("beach");
    if (types.some((x) => ["טיולי פריחה", "נקודות עניין בטבע", "שמורות טבע וגנים לאומיים", "נקודות תצפית", "פארקים לפיקניק", "מסלולי טיול"].includes(x))) cats.push("nature");
    if (types.some((x) => ["פארק שעשועים", "טיולים עם עגלות", "טיולים עם חיות"].includes(x)) || /טרמפולינ|ג'ימבו|פארק שעשוע/.test(hay)) cats.push("kids");
  }
  return cats;
}

// Order stops into a smooth, drivable route: start at the stop nearest the origin
// (the natural entry point — a trip from the south enters from the south), then
// greedily hop to the nearest unvisited stop. This keeps the overall travel
// direction while avoiding the east-west zigzag a pure axis-projection produces.
// Falls back to a southernmost start when no origin is given.
function orderByDirection(stops: Place[], origin: LatLng | null, _area: LatLng): Place[] {
  if (stops.length <= 2) return stops.slice();
  const remaining = stops.slice();
  const entryScore = (origin && isFinite(origin.lat) && isFinite(origin.lng))
    ? (p: LatLng) => hav(origin, p) // nearest to origin = entry point
    : (p: LatLng) => p.lat;         // else southernmost first
  let seed = 0;
  for (let i = 1; i < remaining.length; i++) {
    if (entryScore(remaining[i]) < entryScore(remaining[seed])) seed = i;
  }
  const route = [remaining.splice(seed, 1)[0]];
  while (remaining.length) {
    const last = route[route.length - 1];
    let best = 0;
    for (let i = 1; i < remaining.length; i++) {
      if (hav(last, remaining[i]) < hav(last, remaining[best])) best = i;
    }
    route.push(remaining.splice(best, 1)[0]);
  }
  return route;
}

// ---- model plumbing --------------------------------------------------------
function endpointFor(base: string): string {
  const root = base.replace(/\/+$/, "");
  return /\/chat\/completions$/.test(root) ? root : `${root}/chat/completions`;
}
async function callModel(endpoint: string, key: string, model: string, system: string, user: string, maxTokens: number): Promise<any> {
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
    body: JSON.stringify({
      model,
      messages: [{ role: "system", content: system }, { role: "user", content: user }],
      temperature: 0.5,
      max_tokens: maxTokens,
      response_format: { type: "json_object" },
    }),
  });
  if (!res.ok) throw new Error(`provider ${res.status}: ${await safeText(res)}`);
  const data = await res.json().catch(() => null);
  const content = data?.choices?.[0]?.message?.content;
  if (typeof content !== "string") throw new Error("empty completion");
  const obj = parseJson(content);
  if (!obj) throw new Error("unparseable: " + content.slice(0, 200));
  return obj;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  const base = Deno.env.get("LLM_BASE_URL");
  const key = Deno.env.get("LLM_API_KEY");
  const model = Deno.env.get("LLM_MODEL");
  if (!base || !key || !model) return json({ error: "LLM env not configured" }, 500);
  const endpoint = endpointFor(base);

  let body: any;
  try { body = await req.json(); } catch { return json({ error: "bad json" }, 400); }
  const query: string = typeof body?.query === "string" ? body.query.slice(0, 500) : "";
  const durationHint: string = body?.duration === "full" ? "full" : "half";
  const clientPrefs: string[] = Array.isArray(body?.prefs) ? body.prefs : [];
  if (!query.trim()) return json({ error: "empty query" }, 400);

  try {
    // --- Call A: understand the request -----------------------------------
    const intentSys = [
      "You convert a trip request (Hebrew or English) into JSON, using your knowledge of Israeli geography for WGS84 coordinates.",
      "Output STRICT JSON only — no prose, no markdown fences:",
      '{"origin":{"name":string,"lat":number,"lng":number}|null,"area":{"name":string,"lat":number,"lng":number,"radiusKm":number},"duration":"half"|"full","prefs":string[]}',
      '"area" is where the trip should happen (a city, sub-region, or landmark). Set "radiusKm" to how spread out it is: a single city ~8, a sub-region like the Sharon/Galilee/Carmel ~25, a single landmark ~5.',
      '"origin" is where the traveler starts if stated (used only for travel direction), else null.',
      `"prefs" are short English tokens for stated wishes, each one of: ${PREF_TOKENS.join(", ")}. Empty array if none.`,
      '"duration" is "full" for a full day, otherwise "half".',
    ].join("\n");
    const intent = await callModel(endpoint, key, model, intentSys,
      `Request: ${query}\nDefault duration if unspecified: ${durationHint}`, 300);

    const area = intent?.area;
    if (!area || !isFinite(+area.lat) || !isFinite(+area.lng)) {
      return json({ error: "could not resolve a trip area", intent }, 422);
    }
    const areaPt: LatLng = { lat: +area.lat, lng: +area.lng };
    const radiusKm = Math.min(60, Math.max(3, +area.radiusKm || 12));
    const origin: LatLng | null = intent?.origin && isFinite(+intent.origin.lat) && isFinite(+intent.origin.lng)
      ? { lat: +intent.origin.lat, lng: +intent.origin.lng } : null;
    const duration = intent?.duration === "full" ? "full" : durationHint;
    const prefs = [...new Set([...(Array.isArray(intent?.prefs) ? intent.prefs : []), ...clientPrefs])]
      .filter((p) => PREF_TOKENS.includes(p));

    // --- deterministic geo filter -----------------------------------------
    const data = await getData();
    let cands = data.filter((a) => hav(a, areaPt) <= radiusKm);
    cands = dedupe(cands);
    if (prefs.includes("free")) cands = cands.filter(isFree);
    if (cands.length < 2) { // widen once before giving up
      cands = dedupe(data.filter((a) => hav(a, areaPt) <= radiusKm * 2));
      if (prefs.includes("free")) cands = cands.filter(isFree);
    }
    if (cands.length < 2) return json({ error: "no candidates in area", area: area.name }, 422);
    cands.forEach((a) => (a._cats = classify(a)));
    const pool = cands.slice().sort((a, b) => hav(a, areaPt) - hav(b, areaPt)).slice(0, 60);

    // --- Call B: select & write copy --------------------------------------
    const target = duration === "full" ? 6 : 4;
    const list = pool.map((a, i) => `${i}: ${a.title} [${a._cats!.join(",") || "—"}]`).join("\n");
    const selSys = [
      `You are a local trip planner for Israel, planning around "${area.name}".`,
      "Choose an itinerary ONLY from the numbered candidates. Reply with STRICT JSON only:",
      '{"title":string,"intro":string,"stops":[{"i":number,"cat":string,"why":string,"dur":number}]}',
      `Pick about ${target} stops. "i" must be a candidate index from the list.`,
      `"cat" must be one of: ${CATS.join(", ")}.`,
      "Use AT MOST ONE coffee stop, and favour a variety of categories.",
      "Prefer stops close enough to form a sensible route for the available time — avoid long detours.",
      '"why" is ONE short Hebrew sentence on why the place itself is worth visiting. It MUST be position-independent: never reference where the stop falls in the route. Forbidden words: "לסיום","לפתיחה","ראשון","אחרון","להתחיל","לסיים","first","last","start","end". The route order is decided separately afterwards.',
      '"dur" is minutes (integer, 20-180).',
      `Write "title" and "intro" in Hebrew; "intro" briefly reflects the request and the area "${area.name}".`,
      "Honor the preferences; do not repeat a place.",
    ].join("\n");
    const sel = await callModel(endpoint, key, model, selSys,
      [`Original request: ${query}`, `Area: ${area.name}`, `Preferences: ${prefs.join(", ") || "(none)"}`,
        "Candidates (index: title [categories]):", list].join("\n"), 900);

    if (!sel || !Array.isArray(sel.stops)) return json({ error: "unparseable plan" }, 502);

    // resolve indices -> real pins, dedupe, then order by travel direction
    const seen = new Set<number>();
    const picked: Array<Place & { _cat: string; _why: string; _dur?: number }> = [];
    for (const s of sel.stops) {
      const i = Number(s?.i);
      if (!Number.isInteger(i) || i < 0 || i >= pool.length || seen.has(i)) continue;
      seen.add(i);
      const p = pool[i];
      const dur = Number(s?.dur);
      picked.push({
        ...p,
        _cat: CATS.includes(s?.cat) ? s.cat : (p._cats?.[0] || "attraction"),
        _why: typeof s?.why === "string" ? s.why.slice(0, 160) : "",
        _dur: Number.isFinite(dur) && dur > 0 ? Math.min(240, Math.round(dur)) : undefined,
      });
    }
    if (picked.length < 2) return json({ error: "too few valid stops" }, 502);
    const ordered = orderByDirection(picked, origin, areaPt) as typeof picked;

    return json({
      title: typeof sel.title === "string" ? sel.title.slice(0, 80) : "",
      intro: typeof sel.intro === "string" ? sel.intro.slice(0, 400) : "",
      area: area.name,
      stops: ordered.map((p) => ({
        title: p.title, lat: p.lat, lng: p.lng, cat: p._cat, why: p._why, durMin: p._dur,
      })),
    });
  } catch (e) {
    return json({ error: "agent failed", detail: String(e).slice(0, 300) }, 502);
  }
});

// ---- helpers ---------------------------------------------------------------
function json(obj: unknown, status = 200): Response {
  return new Response(JSON.stringify(obj), { status, headers: { ...cors, "Content-Type": "application/json" } });
}
async function safeText(res: Response): Promise<string> {
  try { return (await res.text()).slice(0, 300); } catch { return ""; }
}
function parseJson(s: string): any {
  try { return JSON.parse(s); } catch { /* fall through */ }
  const m = s.match(/\{[\s\S]*\}/);
  if (m) { try { return JSON.parse(m[0]); } catch { /* give up */ } }
  return null;
}
