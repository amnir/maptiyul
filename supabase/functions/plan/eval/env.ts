// Shared LLM env resolution for the eval harness.
//
// Order of precedence:
//   1. Variables already exported in the shell (LLM_BASE_URL / LLM_API_KEY / LLM_MODEL).
//   2. A KEY=VALUE .env file — `--env-file <path>` if given, else the sibling
//      `supabase/functions/plan/.env` (the same file `dev.ts` reads).
// Shell vars win so you can do `LLM_MODEL=foo deno run ... run.ts` for a one-off
// model without editing .env. The real .env lives in the MAIN clone (gitignored),
// not in throwaway worktrees — see eval/README.md.

import type { PlanEnv } from "../pipeline.ts";

async function loadDotEnv(path: string): Promise<Record<string, string>> {
  let text: string;
  try {
    text = await Deno.readTextFile(path);
  } catch {
    return {};
  }
  const out: Record<string, string> = {};
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
    if (k) out[k] = v;
  }
  return out;
}

export async function resolveEnv(envFile?: string): Promise<PlanEnv & { _source: string }> {
  const path = envFile ?? new URL("../.env", import.meta.url).pathname;
  const file = await loadDotEnv(path);
  const pick = (k: string) => Deno.env.get(k) ?? file[k] ?? undefined;
  const usedFile = Object.keys(file).length > 0;
  return {
    LLM_BASE_URL: pick("LLM_BASE_URL"),
    LLM_API_KEY: pick("LLM_API_KEY"),
    LLM_MODEL: pick("LLM_MODEL"),
    _source: usedFile ? `shell+${path}` : "shell only",
  };
}
