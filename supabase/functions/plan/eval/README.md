# Trip-planner eval harness

Locally grade the trip-planner agent against **gold "god model" reference plans**.
For each *route type* (coastal half-day, family full-day in the Galilee, rainy-day
indoor Tel Aviv, …) `cases.ts` holds an ideal itinerary authored by a top model
(Claude/Opus) from the **same deterministic candidate pool the agent sees**. The
harness runs the real (cheaper) model end-to-end and scores how close it lands.

Everything runs against the same pure `planTrip` pipeline the Edge Function uses
(`../pipeline.ts`) — no deploy, no Supabase.

## Run it

```bash
cd supabase/functions/plan

# offline self-test / naive baseline — no API key needed:
deno run --allow-net eval/run.ts --mock

# live, real model (reads LLM_* from shell env, else ../.env, else --env-file):
deno run --allow-net --allow-env --allow-read eval/run.ts
deno run --allow-net --allow-env --allow-read eval/run.ts --case coastal-sharon-halfday
deno run --allow-net --allow-env --allow-read eval/run.ts --model moonshotai/kimi-k2.6 --runs 3 --report
```

The real `.env` (gitignored, with `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`)
lives in the **main clone** at `supabase/functions/plan/.env` — not in throwaway
worktrees, which get auto-cleaned. Or `export LLM_*` in your shell, or `--env-file`.

### Flags
| flag | meaning |
|---|---|
| `--case a,b` | run only these case ids |
| `--model <id>` | override `LLM_MODEL` for this run (swap the model under test) |
| `--runs <k>` | run each case k times, report mean + range (temp 0.5 ⇒ variance) |
| `--retries <n>` | retry transient provider 5xx (default 2; NIM free tier 429s under burst) |
| `--delay <ms>` | pause between model calls (default 3000) to stay under rate limits |
| `--mock` | deterministic naive nearest-N provider; offline baseline, no key |
| `--report` | write `reports/<model>-<ts>.json` |
| `--json` | print machine-readable result |
| `--env-file <p>` | load env from a specific `.env` |

### Compare two models
```bash
deno run ... eval/run.ts --model minimaxai/minimax-m3 --report
deno run ... eval/run.ts --model moonshotai/kimi-k2.6 --report
deno run --allow-read eval/compare.ts reports/minimaxai_minimax-m3-*.json reports/moonshotai_kimi-k2.6-*.json
```

## Scoring

Each case yields dimensions (0..1, weighted; the overall is a weighted mean over
the dims that apply — e.g. `direction` only counts when the request states an origin):

- **valid** (gate) — HTTP 200 with ≥2 stops; if it fails the case scores 0.
- **areaResolved**, **prefsMatch** — Call-A (intent parse) vs gold, from `_debug`.
- **withinArea** — fraction of stops actually inside the requested area.
- **stopCount**, **coffeeCap**, **categoryVariety** — structural rules.
- **routeCompact** — total haversine route length vs the gold budget.
- **direction** — N→S / S→N matches the travel direction implied by the origin.
- **selectionOverlap** — **the headline metric**: F1 of chosen places vs the god
  model's picks (precision/recall/matched/missed/extra printed per case).
- **copyQuality** — Hebrew title/intro + position-independent `why` (no “first/last/לסיום…”).

## Authoring / refreshing gold

Gold `stops` must be real dataset titles from the agent's candidate pool. Dump that
pool offline (no model call) and pick the ideal itinerary:

```bash
deno run --allow-net eval/dump.ts --case coastal-sharon-halfday
deno run --allow-net eval/dump.ts --lat 32.32 --lng 34.85 --radius 20 --free
```

Then edit `cases.ts`. Re-author after the dataset changes (place titles can shift).
To add a route type: append a `GoldCase` (query + intent + rubric), dump its pool,
fill `stops`.

## How it hangs together
- `cases.ts` — gold route types (intent + rubric + ideal itinerary).
- `dump.ts` — offline pool dumper (reuses `pipeline.buildPool`).
- `score.ts` — pure grading (`scoreCase`).
- `run.ts` — runs the agent per case, prints scorecards + suite average, writes reports.
- `compare.ts` — side-by-side of two reports.
- `env.ts` — shell → `.env` → `--env-file` resolution.
