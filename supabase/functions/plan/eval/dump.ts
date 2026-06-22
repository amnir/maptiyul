// Offline candidate-pool dumper — NO model call, NO API key needed.
//
// Reproduces the exact pool the agent's Call-B chooses from (pipeline.buildPool)
// for a gold case's intent, so you can author the gold `stops` from real titles.
//
//   deno run --allow-net eval/dump.ts --case coastal-sharon-halfday
//   deno run --allow-net eval/dump.ts --lat 32.32 --lng 34.85 --radius 20 [--free]
//
// Prints "i: title [cats]  (d km from area)" for the nearest 60 candidates.

import { buildPool, getData, hav, type LatLng } from "../pipeline.ts";
import { byId } from "./cases.ts";

function arg(name: string): string | undefined {
  const i = Deno.args.indexOf(`--${name}`);
  return i >= 0 ? Deno.args[i + 1] : undefined;
}
const has = (name: string) => Deno.args.includes(`--${name}`);

let area: LatLng, radiusKm: number, prefs: string[], label: string;
const caseId = arg("case");
if (caseId) {
  const c = byId(caseId);
  if (!c) {
    console.error(`unknown case "${caseId}"`);
    Deno.exit(1);
  }
  area = { lat: c.area.lat, lng: c.area.lng };
  radiusKm = c.area.radiusKm;
  prefs = c.prefs ?? [];
  label = `${c.id} — ${c.area.name} r${radiusKm}km prefs[${prefs.join(",")}]`;
} else {
  const lat = Number(arg("lat")), lng = Number(arg("lng"));
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    console.error("provide --case <id>  OR  --lat <n> --lng <n> [--radius 12] [--free]");
    Deno.exit(1);
  }
  area = { lat, lng };
  radiusKm = Number(arg("radius") ?? 12);
  prefs = has("free") ? ["free"] : [];
  label = `lat ${lat} lng ${lng} r${radiusKm}km prefs[${prefs.join(",")}]`;
}

const data = await getData({ fetch: (...a) => fetch(...a) });
const pool = buildPool(data, area, radiusKm, prefs);
console.log(`# pool for ${label}\n# ${pool.length} candidates (showing nearest first)\n`);
pool.forEach((p, i) => {
  const d = hav(area, p).toFixed(1);
  console.log(`${String(i).padStart(2)}: ${p.title}  [${(p._cats ?? []).join(",") || "—"}]  (${d}km)`);
});
