// Local prompt/model iteration harness for the trip-planner agent — no deploy.
//
// Loads supabase/functions/plan/.env, runs the SAME pure pipeline the Edge
// Function uses (pipeline.ts), and pretty-prints the plan with per-leg haversine
// distances and the coffee count (the manual checks used while tuning).
//
//   deno run --allow-net --allow-env --allow-read \
//     supabase/functions/plan/dev.ts "<query>" [half|full]
//
// Example:
//   deno run --allow-net --allow-env --allow-read \
//     supabase/functions/plan/dev.ts "אני מרמת גן, רוצה טיול חצי יום בשרון"

import { hav, planTrip, type LatLng } from "./pipeline.ts";

// Minimal KEY=VALUE .env loader (sibling .env). Avoids a 3rd-party dep.
async function loadEnv(path: string): Promise<void> {
  let text: string;
  try {
    text = await Deno.readTextFile(path);
  } catch {
    console.error(`Could not read ${path} — copy .env.example to .env and fill in real values.`);
    Deno.exit(1);
  }
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const k = line.slice(0, eq).trim();
    let v = line.slice(eq + 1).trim();
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      v = v.slice(1, -1);
    }
    if (k) Deno.env.set(k, v);
  }
}

function fmt(n: number): string {
  return n.toFixed(1);
}

const args = Deno.args;
const query = args[0];
const duration = args[1] === "full" ? "full" : args[1] === "half" ? "half" : undefined;
if (!query) {
  console.error('Usage: deno run --allow-net --allow-env --allow-read dev.ts "<query>" [half|full]');
  Deno.exit(1);
}

const here = new URL("./.env", import.meta.url).pathname;
await loadEnv(here);

const env = {
  LLM_BASE_URL: Deno.env.get("LLM_BASE_URL"),
  LLM_API_KEY: Deno.env.get("LLM_API_KEY"),
  LLM_MODEL: Deno.env.get("LLM_MODEL"),
};
console.log(`model: ${env.LLM_MODEL}  base: ${env.LLM_BASE_URL}`);
console.log(`query: ${query}${duration ? `  duration: ${duration}` : ""}\n`);

const { status, body } = await planTrip({ query, duration }, env);

if (status !== 200) {
  console.error(`HTTP ${status}:`, JSON.stringify(body, null, 2));
  Deno.exit(1);
}

const plan = body as {
  title: string; intro: string; area: string;
  stops: Array<{ title: string; lat: number; lng: number; cat: string; why: string; durMin?: number }>;
};

console.log(`# ${plan.title}`);
console.log(`area: ${plan.area}`);
console.log(`${plan.intro}\n`);

let totalKm = 0;
let coffee = 0;
let prev: LatLng | null = null;
plan.stops.forEach((s, i) => {
  let leg = "";
  if (prev) {
    const d = hav(prev, s);
    totalKm += d;
    leg = `  (+${fmt(d)} km)`;
  }
  if (s.cat === "coffee") coffee++;
  console.log(`${i + 1}. ${s.title}  [${s.cat}${s.durMin ? `, ${s.durMin}m` : ""}]${leg}`);
  console.log(`   lat ${s.lat}, lng ${s.lng}`);
  if (s.why) console.log(`   ${s.why}`);
  prev = s;
});

console.log(`\nstops: ${plan.stops.length}   total route: ${fmt(totalKm)} km   coffee stops: ${coffee}`);
console.log(`order: ${plan.stops[0]?.lat > plan.stops[plan.stops.length - 1]?.lat ? "north→south" : "south→north"} (by latitude of first vs last)`);
