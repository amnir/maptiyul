// Vendor-agnostic LLM trip-planner agent (Supabase Edge Function, Deno).
//
// This file is only the HTTP wrapper: CORS, method handling, request-body
// parsing, and reading env. The actual two-step pipeline lives in `pipeline.ts`
// as a pure, importable `planTrip(body, env, deps)` so it can be exercised
// locally without a deploy (see `dev.ts` and the README's "Trip planner (LLM
// backend)" section). Keep this wrapper's request/response shapes, CORS, and
// error statuses in sync with the pure function.

import { planTrip } from "./pipeline.ts";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  let body: any;
  try { body = await req.json(); } catch { return json({ error: "bad json" }, 400); }

  const { status, body: out } = await planTrip(body, {
    LLM_BASE_URL: Deno.env.get("LLM_BASE_URL"),
    LLM_API_KEY: Deno.env.get("LLM_API_KEY"),
    LLM_MODEL: Deno.env.get("LLM_MODEL"),
  });
  return json(out, status);
});

function json(obj: unknown, status = 200): Response {
  return new Response(JSON.stringify(obj), { status, headers: { ...cors, "Content-Type": "application/json" } });
}
