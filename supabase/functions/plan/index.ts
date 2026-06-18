// Vendor-agnostic LLM trip-planner proxy (Supabase Edge Function, Deno).
//
// Reads provider config from environment ONLY (never committed):
//   LLM_BASE_URL  OpenAI-compatible /v1 root, e.g. https://integrate.api.nvidia.com/v1
//   LLM_API_KEY   provider key (set via `supabase secrets set`)
//   LLM_MODEL     model id string for the chosen provider
//
// The client sends a compact, pre-filtered candidate list; the model selects and
// orders stops BY INDEX (so it cannot invent coordinates) and writes Hebrew copy.
// Response shape consumed by index.html:
//   { title, intro, stops: [{ i, cat, why, dur }] }
// No dataset and no secrets live here — this is a stateless proxy.

const cors = {
  "Access-Control-Allow-Origin": "*", // public, no-credential endpoint; tighten if needed
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

// Must match the CAT keys in index.html.
const CATS = ["coffee", "indoor", "beach", "nature", "kids", "attraction"];

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  const base = Deno.env.get("LLM_BASE_URL");
  const key = Deno.env.get("LLM_API_KEY");
  const model = Deno.env.get("LLM_MODEL");
  if (!base || !key || !model) return json({ error: "LLM env not configured" }, 500);

  let body: any;
  try {
    body = await req.json();
  } catch {
    return json({ error: "bad json" }, 400);
  }

  const query: string = typeof body?.query === "string" ? body.query : "";
  const duration: string = body?.duration === "full" ? "full" : "half";
  const mustHaves: string[] = Array.isArray(body?.mustHaves) ? body.mustHaves : [];
  const candidates: any[] = Array.isArray(body?.candidates) ? body.candidates : [];
  if (candidates.length < 2) return json({ error: "need >= 2 candidates" }, 400);

  const target = duration === "full" ? 6 : 4;
  const list = candidates
    .slice(0, 80)
    .map((c) => `${c.i}: ${c.title} [${Array.isArray(c.cats) && c.cats.length ? c.cats.join(",") : "—"}]`)
    .join("\n");

  const sys = [
    "You are a local trip planner for the Netanya / Sharon area in Israel.",
    "Build an ordered itinerary chosen ONLY from the numbered candidates provided.",
    "Reply with STRICT JSON only — no prose, no markdown fences — matching:",
    '{"title": string, "intro": string, "stops": [{"i": number, "cat": string, "why": string, "dur": number}]}',
    `Pick about ${target} stops. "i" must be a candidate index from the list.`,
    `"cat" must be one of: ${CATS.join(", ")}.`,
    '"why" is one short sentence in Hebrew. "dur" is minutes (integer, 20-180).',
    'Write "title" and "intro" in Hebrew; "intro" briefly reflects the user\'s request.',
    "Honor the must-haves and the free-text request. Do not repeat a place.",
  ].join("\n");

  const user = [
    `User request (Hebrew): ${query || "(none)"}`,
    `Must-haves: ${mustHaves.join(", ") || "(none)"}`,
    `Duration: ${duration}`,
    "Candidates (index: title [categories]):",
    list,
  ].join("\n");

  let res: Response;
  try {
    res = await fetch(`${base.replace(/\/$/, "")}/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
      body: JSON.stringify({
        model,
        messages: [
          { role: "system", content: sys },
          { role: "user", content: user },
        ],
        temperature: 0.6,
        max_tokens: 900,
        response_format: { type: "json_object" }, // honored by most OpenAI-compatible providers
      }),
    });
  } catch (e) {
    return json({ error: "provider unreachable", detail: String(e) }, 502);
  }
  if (!res.ok) return json({ error: "provider error", status: res.status, detail: await safeText(res) }, 502);

  const data = await res.json().catch(() => null);
  const content = data?.choices?.[0]?.message?.content;
  if (typeof content !== "string") return json({ error: "empty completion" }, 502);

  const plan = parseJson(content);
  if (!plan || !Array.isArray(plan.stops)) return json({ error: "unparseable plan", raw: content.slice(0, 400) }, 502);

  // Sanitize: keep only valid, in-range, non-duplicate indices.
  const seen = new Set<number>();
  const stops: any[] = [];
  for (const s of plan.stops) {
    const i = Number(s?.i);
    if (!Number.isInteger(i) || i < 0 || i >= candidates.length || seen.has(i)) continue;
    seen.add(i);
    const dur = Number(s?.dur);
    stops.push({
      i,
      cat: CATS.includes(s?.cat) ? s.cat : "attraction",
      why: typeof s?.why === "string" ? s.why.slice(0, 160) : "",
      dur: Number.isFinite(dur) && dur > 0 ? Math.min(240, Math.round(dur)) : undefined,
    });
  }
  if (stops.length < 2) return json({ error: "too few valid stops", raw: content.slice(0, 400) }, 502);

  return json({
    title: typeof plan.title === "string" ? plan.title.slice(0, 80) : "",
    intro: typeof plan.intro === "string" ? plan.intro.slice(0, 400) : "",
    stops,
  });
});

function json(obj: unknown, status = 200): Response {
  return new Response(JSON.stringify(obj), { status, headers: { ...cors, "Content-Type": "application/json" } });
}

async function safeText(res: Response): Promise<string> {
  try {
    return (await res.text()).slice(0, 300);
  } catch {
    return "";
  }
}

// Tolerate providers that wrap JSON in prose or ```json fences.
function parseJson(s: string): any {
  try {
    return JSON.parse(s);
  } catch {
    /* fall through */
  }
  const m = s.match(/\{[\s\S]*\}/);
  if (m) {
    try {
      return JSON.parse(m[0]);
    } catch {
      /* give up */
    }
  }
  return null;
}
