// Trip-planner eval harness — run the agent over the gold route-types and grade
// each plan against the "god model" reference itineraries in cases.ts.
//
//   # live (real model from .env / shell env):
//   deno run --allow-net --allow-env --allow-read eval/run.ts
//   deno run --allow-net --allow-env --allow-read eval/run.ts --case coastal-sharon-halfday
//   deno run --allow-net --allow-env --allow-read eval/run.ts --model moonshotai/kimi-k2.6 --runs 3 --report
//
//   # offline self-test / naive baseline (no key, deterministic nearest-N picker):
//   deno run --allow-net eval/run.ts --mock
//
// Flags: --case <id[,id...]>  --model <id>  --runs <k>  --env-file <path>
//        --mock  --json  --report  --debug
//
// `--report` writes reports/<model>-<ts>.json; compare two with compare.ts.

import { type PlanDeps, type PlanEnv, planTrip } from "../pipeline.ts";
import { resolveEnv } from "./env.ts";
import { CASES } from "./cases.ts";
import { type CaseScore, type GoldCase, scoreCase } from "./score.ts";

// ---- args ------------------------------------------------------------------
const arg = (n: string): string | undefined => {
  const i = Deno.args.indexOf(`--${n}`);
  return i >= 0 ? Deno.args[i + 1] : undefined;
};
const has = (n: string) => Deno.args.includes(`--${n}`);
const MOCK = has("mock");
const JSON_OUT = has("json");
const REPORT = has("report");
const SHOW_DEBUG = has("debug");
const RUNS = Math.max(1, Number(arg("runs") ?? 1));
const RETRIES = Math.max(0, Number(arg("retries") ?? 2)); // retry transient provider 5xx
const DELAY = Math.max(0, Number(arg("delay") ?? 3000)); // ms between calls (NIM free tier 429s under burst)
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const onlyIds = (arg("case") ?? "").split(",").map((s) => s.trim()).filter(Boolean);
const cases = onlyIds.length ? CASES.filter((c) => onlyIds.includes(c.id)) : CASES;
if (!cases.length) {
  console.error("no matching cases");
  Deno.exit(1);
}

// ---- mock provider: real dataset, deterministic naive picker ---------------
// Call A returns the gold intent (isolates Call-B); Call B picks the first
// `target` pool candidates. A trivial baseline to compare real models against.
function mockDeps(gold: GoldCase): PlanDeps {
  return {
    fetch: async (input: string | URL | Request, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("attractions.json")) return fetch(input as any, init);
      const reqBody = JSON.parse(String(init?.body ?? "{}"));
      const sys = String(reqBody.messages?.[0]?.content ?? "");
      const usr = String(reqBody.messages?.[1]?.content ?? "");
      let obj: unknown;
      if (sys.startsWith("You convert a trip request")) {
        obj = {
          origin: gold.origin ?? null,
          area: { name: gold.area.name, lat: gold.area.lat, lng: gold.area.lng, radiusKm: gold.area.radiusKm },
          duration: gold.duration ?? "half",
          prefs: gold.prefs ?? [],
        };
      } else {
        const target = (gold.duration === "full") ? 6 : 4;
        const idx = [...usr.matchAll(/^(\d+): .+\[([^\]]*)\]/gm)].slice(0, target);
        obj = {
          title: "מסלול לדוגמה",
          intro: "מסלול בדיקה אוטומטי באזור.",
          stops: idx.map((m) => ({
            i: Number(m[1]),
            cat: (m[2].split(",")[0] || "attraction").trim(),
            why: "מקום נחמד לביקור באזור.",
            dur: 60,
          })),
        };
      }
      return new Response(JSON.stringify({ choices: [{ message: { content: JSON.stringify(obj) } }] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    },
  };
}

// ---- env -------------------------------------------------------------------
let env: PlanEnv & { _source?: string };
let modelLabel: string;
if (MOCK) {
  env = { LLM_BASE_URL: "http://mock/v1", LLM_API_KEY: "mock", LLM_MODEL: "mock-naive-nearestN" };
  modelLabel = "mock-naive-nearestN";
} else {
  env = await resolveEnv(arg("env-file"));
  const modelOverride = arg("model");
  if (modelOverride) env.LLM_MODEL = modelOverride;
  modelLabel = env.LLM_MODEL ?? "(unset)";
  if (!env.LLM_BASE_URL || !env.LLM_API_KEY || !env.LLM_MODEL) {
    console.error(
      `LLM env incomplete (${env._source}). Set LLM_BASE_URL / LLM_API_KEY / LLM_MODEL in the\n` +
        `main clone's supabase/functions/plan/.env (gitignored), export them in your shell, or\n` +
        `pass --env-file <path>. To try the harness with no key: --mock`,
    );
    Deno.exit(1);
  }
}

// ---- run -------------------------------------------------------------------
const bar = (x: number, n = 10) => "█".repeat(Math.round(x * n)).padEnd(n, "·");
const pct = (x: number) => (x * 100).toFixed(0).padStart(3) + "%";

// Wrap deps.fetch to time each model (chat/completions) call. The dataset fetch
// is excluded so latency reflects only the LLM round-trips (Call-A + Call-B),
// which is what the 45s client timeout actually races against.
function timingDeps(inner: PlanDeps | undefined): { deps: PlanDeps; calls: number[] } {
  const base = inner ?? { fetch: (...a: Parameters<typeof fetch>) => fetch(...a) };
  const calls: number[] = [];
  return {
    calls,
    deps: {
      fetch: async (input: any, init?: any) => {
        const url = typeof input === "string" ? input : input.toString();
        const isModel = url.includes("/chat/completions") || url.includes("/mock/");
        const t0 = performance.now();
        const res = await base.fetch(input, init);
        if (isModel) calls.push(performance.now() - t0);
        return res;
      },
    },
  };
}

type RunTiming = { totalMs: number; callsMs: number[] };
type CaseAgg = {
  gold: GoldCase;
  runs: CaseScore[];
  timings: RunTiming[];
  mean: number;
  minO: number;
  maxO: number;
  medMs: number;
};
const aggs: CaseAgg[] = [];
const median = (xs: number[]) => {
  if (!xs.length) return NaN;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

console.log(`\n🧭 trip-planner eval — model: ${modelLabel}  cases: ${cases.length}  runs/case: ${RUNS}\n`);

for (const gold of cases) {
  const runs: CaseScore[] = [];
  const timings: RunTiming[] = [];
  for (let r = 0; r < RUNS; r++) {
    // Retry transient provider failures (5xx) so the score reflects plan quality,
    // not NIM's reliability under back-to-back load. A 4xx/422 is the model's own
    // output, not transient — don't retry those.
    let status = 0, body: unknown = {}, callsMs: number[] = [], totalMs = 0;
    for (let attempt = 0; attempt <= RETRIES; attempt++) {
      const { deps, calls } = timingDeps(MOCK ? mockDeps(gold) : undefined);
      const t0 = performance.now();
      ({ status, body } = await planTrip({ query: gold.query, duration: gold.duration }, env, deps, { debug: true }));
      totalMs = performance.now() - t0;
      callsMs = calls;
      if (status === 200 || status < 500 || MOCK) break;
      if (attempt < RETRIES) {
        console.error(`  … ${gold.id} HTTP ${status}, retry ${attempt + 1}/${RETRIES}`);
        await sleep(2500 * (attempt + 1));
      }
    }
    runs.push(scoreCase(gold, status, body));
    timings.push({ totalMs, callsMs });
    if (SHOW_DEBUG && r === 0) console.error(`\n[debug ${gold.id}]`, JSON.stringify(body, null, 2).slice(0, 1500));
    if (!MOCK) await sleep(DELAY); // ease rate limits between calls
  }
  const overalls = runs.map((s) => s.overall);
  const mean = overalls.reduce((a, b) => a + b, 0) / overalls.length;
  const medMs = median(timings.map((t) => t.totalMs));
  const agg: CaseAgg = { gold, runs, timings, mean, minO: Math.min(...overalls), maxO: Math.max(...overalls), medMs };
  aggs.push(agg);

  // print the most recent run's full scorecard
  const last = runs[runs.length - 1];
  const lastT = timings[timings.length - 1];
  const spread = RUNS > 1 ? `  (range ${pct(agg.minO)}–${pct(agg.maxO)} over ${RUNS})` : "";
  const secs = (ms: number) => (ms / 1000).toFixed(1) + "s";
  const legs = lastT.callsMs.map(secs).join(" + ");
  const TIMEOUT_MS = 45_000; // client fetch timeout — past this the UI silently falls back
  const slow = agg.medMs >= TIMEOUT_MS ? "  ⛔ EXCEEDS 45s client timeout" : agg.medMs >= TIMEOUT_MS * 0.8 ? "  ⚠ near 45s timeout" : "";
  console.log(`■ ${gold.id}  «${gold.routeType}»`);
  console.log(`  overall ${pct(mean)} ${bar(mean)}  HTTP ${last.status}${spread}`);
  console.log(`  latency ${secs(agg.medMs)}${RUNS > 1 ? " (median)" : ""}  [${legs || "—"}]${slow}`);
  if (last.error) console.log(`  error: ${last.error}`);
  for (const d of last.dims) {
    console.log(`    ${d.dim.padEnd(16)} ${pct(d.score)} ${bar(d.score)}  ${d.note}`);
  }
  if (last.selection) {
    const s = last.selection;
    console.log(`    selection: matched [${s.matched.join(" | ") || "—"}]`);
    if (s.missedGold.length) console.log(`               missed gold [${s.missedGold.join(" | ")}]`);
    if (s.extra.length) console.log(`               extra [${s.extra.join(" | ")}]`);
  }
  console.log("");
}

// ---- aggregate -------------------------------------------------------------
const suiteMean = aggs.reduce((a, x) => a + x.mean, 0) / aggs.length;
const allMs = aggs.map((a) => a.medMs).filter((x) => Number.isFinite(x));
const suiteMedMs = median(allMs);
const slowest = aggs.slice().sort((a, b) => b.medMs - a.medMs)[0];
const s1 = (ms: number) => (ms / 1000).toFixed(1) + "s";
console.log("─".repeat(60));
console.log(`SUITE  ${modelLabel}`);
for (const a of aggs) console.log(`  ${pct(a.mean)} ${bar(a.mean)}  ${s1(a.medMs).padStart(6)}  ${a.gold.id}`);
console.log(`  ────`);
console.log(`  ${pct(suiteMean)} ${bar(suiteMean)}  ${s1(suiteMedMs).padStart(6)}  AVERAGE (median latency)`);
if (slowest) console.log(`  slowest: ${slowest.gold.id} @ ${s1(slowest.medMs)}${slowest.medMs >= 45000 ? "  ⛔ >45s" : slowest.medMs >= 36000 ? "  ⚠ near 45s" : ""}`);
console.log("─".repeat(60));

// ---- machine output / report ----------------------------------------------
const result = {
  model: modelLabel,
  ranAt: new Date().toISOString(),
  runsPerCase: RUNS,
  suiteMean,
  suiteMedianMs: suiteMedMs,
  cases: aggs.map((a) => ({
    id: a.gold.id,
    routeType: a.gold.routeType,
    mean: a.mean,
    min: a.minO,
    max: a.maxO,
    medianMs: a.medMs,
    callsMs: a.timings[a.timings.length - 1].callsMs,
    last: a.runs[a.runs.length - 1],
  })),
};
if (JSON_OUT) console.log(JSON.stringify(result, null, 2));
if (REPORT) {
  const dir = new URL("./reports/", import.meta.url).pathname;
  await Deno.mkdir(dir, { recursive: true });
  const safe = modelLabel.replace(/[^a-z0-9._-]+/gi, "_");
  const path = `${dir}${safe}-${Date.now()}.json`;
  await Deno.writeTextFile(path, JSON.stringify(result, null, 2));
  console.log(`\nreport written: ${path}`);
}
