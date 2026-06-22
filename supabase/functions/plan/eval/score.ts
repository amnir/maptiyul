// Pure scoring: grade one model plan against one gold case.
//
// The gold case is the "god model" reference authored by a top model (Claude/Opus)
// from the SAME deterministic candidate pool the agent sees (see dump.ts / README).
// Every dimension is 0..1 with a human-readable note; the overall is a weighted
// mean over the dimensions that apply to this case (skipped dims drop out of the
// denominator, so cases without an origin aren't penalised on "direction", etc.).

import { hav, type LatLng } from "../pipeline.ts";

export type GoldStop = { title: string; cat?: string };
export type GoldCase = {
  id: string;
  routeType: string; // e.g. "coastal-halfday", "family-north-fullday"
  query: string; // the Hebrew free-text request fed to the agent
  duration?: "half" | "full";
  // Call-A expectation (resolved intent):
  area: { name: string; lat: number; lng: number; radiusKm: number };
  origin?: LatLng | null;
  prefs?: string[];
  // Call-B expectation (ideal ordered itinerary; titles are real dataset titles):
  stops: GoldStop[];
  // rubric / tolerances:
  maxRouteKm: number; // a good route for this request fits in this many km
  stopCountTol?: number; // allowed |actual-gold| stop-count slack (default 1)
  notes?: string;
};

export type ActualStop = {
  title: string;
  lat: number;
  lng: number;
  cat: string;
  why: string;
  durMin?: number;
};
export type ActualDebug = {
  area?: { name: string; lat: number; lng: number; radiusKm: number };
  origin?: LatLng | null;
  duration?: string;
  prefs?: string[];
  poolSize?: number;
  pool?: { title: string; cats: string[] }[];
};
export type ActualPlan = {
  title?: string;
  intro?: string;
  area?: string;
  stops?: ActualStop[];
  _debug?: ActualDebug;
};

export type DimScore = { dim: string; score: number; weight: number; note: string };
export type Selection = {
  precision: number;
  recall: number;
  f1: number;
  matched: string[];
  missedGold: string[];
  extra: string[];
};
export type CaseScore = {
  id: string;
  routeType: string;
  status: number;
  overall: number;
  dims: DimScore[];
  selection?: Selection;
  error?: string;
};

const FORBIDDEN_POS = ["לסיום", "לפתיחה", "ראשון", "אחרון", "להתחיל", "לסיים", "first", "last", "start", "end"];
const hasHebrew = (s: string) => /[֐-׿]/.test(s);
const norm = (s: string) => (s ?? "").trim();

// Linear decay: full credit at/under `good`, zero at/over `bad`, linear between.
function decay(value: number, good: number, bad: number): number {
  if (value <= good) return 1;
  if (value >= bad) return 0;
  return (bad - value) / (bad - good);
}

function jaccard(a: string[], b: string[]): number {
  const A = new Set(a), B = new Set(b);
  if (A.size === 0 && B.size === 0) return 1;
  let inter = 0;
  for (const x of A) if (B.has(x)) inter++;
  return inter / (A.size + B.size - inter);
}

function prf(actual: string[], gold: string[]): Selection {
  const A = new Set(actual.map(norm)), G = new Set(gold.map(norm));
  const matched = [...A].filter((x) => G.has(x));
  const precision = A.size ? matched.length / A.size : 0;
  const recall = G.size ? matched.length / G.size : 0;
  const f1 = precision + recall ? (2 * precision * recall) / (precision + recall) : 0;
  return {
    precision,
    recall,
    f1,
    matched,
    missedGold: [...G].filter((x) => !A.has(x)),
    extra: [...A].filter((x) => !G.has(x)),
  };
}

function routeKm(stops: ActualStop[]): number {
  let km = 0;
  for (let i = 1; i < stops.length; i++) km += hav(stops[i - 1], stops[i]);
  return km;
}

export function scoreCase(gold: GoldCase, status: number, body: unknown): CaseScore {
  const dims: DimScore[] = [];
  const add = (dim: string, score: number, weight: number, note: string) =>
    dims.push({ dim, score, weight, note });

  // --- hard validity gate -------------------------------------------------
  const plan = (body && typeof body === "object" ? body : {}) as ActualPlan;
  const stops = Array.isArray(plan.stops) ? plan.stops : [];
  const ok = status === 200 && stops.length >= 2;
  add("valid", ok ? 1 : 0, 3, ok ? `HTTP 200, ${stops.length} stops` : `HTTP ${status}, ${stops.length} stops`);
  if (!ok) {
    const b = (body ?? {}) as any;
    const err = [b.error, b.detail].filter(Boolean).map(String).join(" — ") || `HTTP ${status}`;
    return { id: gold.id, routeType: gold.routeType, status, overall: 0, dims, error: err };
  }

  const dbg = plan._debug;
  const goldArea: LatLng = { lat: gold.area.lat, lng: gold.area.lng };

  // --- Call-A: area resolution (needs _debug) -----------------------------
  if (dbg?.area && Number.isFinite(dbg.area.lat) && Number.isFinite(dbg.area.lng)) {
    const d = hav(goldArea, { lat: dbg.area.lat, lng: dbg.area.lng });
    add("areaResolved", decay(d, gold.area.radiusKm, gold.area.radiusKm * 3), 2,
      `${d.toFixed(1)}km from gold "${gold.area.name}" (got "${dbg.area.name}")`);
  }

  // --- Call-A: prefs parse (needs _debug) ---------------------------------
  if (dbg?.prefs) {
    const j = jaccard(dbg.prefs, gold.prefs ?? []);
    add("prefsMatch", j, 1, `got [${dbg.prefs.join(",")}] vs gold [${(gold.prefs ?? []).join(",")}]`);
  }

  // --- geography: stops actually in the requested area --------------------
  const areaTol = Math.max(gold.area.radiusKm * 1.5, 8);
  const inArea = stops.filter((s) => hav(goldArea, s) <= areaTol).length;
  add("withinArea", inArea / stops.length, 2, `${inArea}/${stops.length} within ${areaTol.toFixed(0)}km of area`);

  // --- structure: stop count ----------------------------------------------
  const tol = gold.stopCountTol ?? 1;
  const diff = Math.abs(stops.length - gold.stops.length);
  add("stopCount", decay(diff, tol, tol + 3), 1, `${stops.length} stops vs gold ${gold.stops.length} (±${tol})`);

  // --- structure: at most one coffee --------------------------------------
  const coffee = stops.filter((s) => s.cat === "coffee").length;
  add("coffeeCap", coffee <= 1 ? 1 : 0, 1, `${coffee} coffee stop(s)`);

  // --- structure: category variety ----------------------------------------
  const cats = new Set(stops.map((s) => s.cat));
  add("categoryVariety", cats.size / stops.length, 1, `${cats.size} distinct cats over ${stops.length} stops`);

  // --- geometry: route compactness ----------------------------------------
  const km = routeKm(stops);
  add("routeCompact", decay(km, gold.maxRouteKm, gold.maxRouteKm * 2.5), 2,
    `${km.toFixed(1)}km route (gold max ${gold.maxRouteKm}km)`);

  // --- geometry: travel direction (only when an origin is stated) ----------
  if (gold.origin && Number.isFinite(gold.origin.lat) && gold.stops.length >= 2) {
    // gold stops are authored in intended visiting order; compare N→S vs S→N sign.
    const actualDir = stops[0].lat >= stops[stops.length - 1].lat ? "N→S" : "S→N";
    // gold direction inferred from origin vs area latitude (enters from origin side).
    const goldDir = gold.origin.lat >= gold.area.lat ? "N→S" : "S→N";
    add("direction", actualDir === goldDir ? 1 : 0, 1, `route ${actualDir}, expected ${goldDir}`);
  }

  // --- selection overlap vs the god model (the headline metric) -----------
  const sel = prf(stops.map((s) => s.title), gold.stops.map((s) => s.title));
  add("selectionOverlap", sel.f1, 3, `F1 ${sel.f1.toFixed(2)} (P ${sel.precision.toFixed(2)}/R ${sel.recall.toFixed(2)})`);

  // --- copy quality -------------------------------------------------------
  let copy = 1;
  const cnotes: string[] = [];
  if (!norm(plan.title ?? "") || !hasHebrew(plan.title ?? "")) { copy -= 0.25; cnotes.push("title weak"); }
  if (!norm(plan.intro ?? "") || !hasHebrew(plan.intro ?? "")) { copy -= 0.25; cnotes.push("intro weak"); }
  const badWhy = stops.filter((s) => {
    const w = norm(s.why);
    return !w || !hasHebrew(w) || FORBIDDEN_POS.some((f) => w.includes(f));
  }).length;
  if (badWhy) { copy -= Math.min(0.5, 0.15 * badWhy); cnotes.push(`${badWhy} weak/positional why`); }
  add("copyQuality", Math.max(0, copy), 1, cnotes.join("; ") || "title+intro+why all Hebrew & position-independent");

  const wsum = dims.reduce((a, d) => a + d.weight, 0);
  const overall = dims.reduce((a, d) => a + d.score * d.weight, 0) / (wsum || 1);
  return { id: gold.id, routeType: gold.routeType, status, overall, dims, selection: sel };
}
