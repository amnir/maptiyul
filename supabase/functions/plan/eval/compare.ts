// Side-by-side compare of two eval reports (written by `run.ts --report`).
//
//   deno run --allow-read eval/compare.ts reports/A.json reports/B.json
//
// Prints per-case overall for each model and the B−A delta, so you can see where
// a model gains or loses against the god-model reference (or another model).

type Report = {
  model: string;
  suiteMean: number;
  suiteMedianMs?: number;
  cases: { id: string; mean: number; medianMs?: number }[];
};

const [pa, pb] = Deno.args;
if (!pa || !pb) {
  console.error("usage: compare.ts <reportA.json> <reportB.json>");
  Deno.exit(1);
}
const A: Report = JSON.parse(await Deno.readTextFile(pa));
const B: Report = JSON.parse(await Deno.readTextFile(pb));

const pct = (x: number) => (x * 100).toFixed(0).padStart(4) + "%";
const sgn = (x: number) => (x >= 0 ? "+" : "") + (x * 100).toFixed(0) + "pp";
const s1 = (ms?: number) => (Number.isFinite(ms) ? (ms! / 1000).toFixed(1) + "s" : "  —").padStart(6);
const ids = [...new Set([...A.cases.map((c) => c.id), ...B.cases.map((c) => c.id)])];
const get = (r: Report, id: string) => r.cases.find((c) => c.id === id);

console.log(`\nA = ${A.model}`);
console.log(`B = ${B.model}\n`);
console.log(`${"case".padEnd(30)} ${"A".padStart(5)} ${"B".padStart(5)}  Δ(B−A)   ${"A lat".padStart(6)} ${"B lat".padStart(6)}`);
console.log("─".repeat(74));
for (const id of ids) {
  const ca = get(A, id), cb = get(B, id);
  const a = ca?.mean ?? NaN, b = cb?.mean ?? NaN;
  const d = b - a;
  const mark = Number.isFinite(d) ? (d > 0.02 ? "▲" : d < -0.02 ? "▼" : "·") : " ";
  console.log(`${id.padEnd(30)} ${pct(a)} ${pct(b)}  ${sgn(d).padStart(6)} ${mark}   ${s1(ca?.medianMs)} ${s1(cb?.medianMs)}`);
}
console.log("─".repeat(74));
console.log(`${"SUITE".padEnd(30)} ${pct(A.suiteMean)} ${pct(B.suiteMean)}  ${sgn(B.suiteMean - A.suiteMean).padStart(6)}     ${s1(A.suiteMedianMs)} ${s1(B.suiteMedianMs)}`);
const fa = A.suiteMedianMs, fb = B.suiteMedianMs;
if (Number.isFinite(fa) && Number.isFinite(fb)) {
  const faster = fa! < fb! ? A.model : B.model;
  console.log(`\nfaster overall: ${faster}  (Δ ${Math.abs((fa! - fb!) / 1000).toFixed(1)}s median per plan)`);
}
