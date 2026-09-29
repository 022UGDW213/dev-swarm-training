// brain.cpp client for Cloudflare Workers.
// Used by the fleet /model relay: try brain.cpp first, fall back to ibot-vault.
//
// env needs: BRAIN_URL (e.g. http://ibot-si:9008), BRAIN_TOKEN,
//            BRAIN_ENABLED ("1" to try brain first).
// Returns the generated text, or null when brain is disabled/unset.
// Throws on reachable-but-erroring brain so the caller can decide to fall back.

export async function brainPredict(env, prompt, opts = {}) {
  if (env.BRAIN_ENABLED !== "1" || !env.BRAIN_URL || !env.BRAIN_TOKEN) return null;
  const url = String(env.BRAIN_URL).replace(/\/$/, "") + "/predict";
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), opts.timeoutMs ?? 60000);
  try {
    const r = await fetch(url, {
      method: "POST",
      signal: ctl.signal,
      headers: {
        "content-type": "application/json",
        "authorization": "Bearer " + env.BRAIN_TOKEN,
      },
      body: JSON.stringify({
        prompt: String(prompt).slice(0, 8000),
        max_tokens: opts.maxTokens ?? 256,
        temperature: opts.temperature ?? 0.0,
        model: opts.model,
      }),
    });
    if (r.status === 409) return null; // native-only model: fall back to vault
    if (!r.ok) throw new Error("brain /predict -> " + r.status);
    const j = await r.json();
    return typeof j.text === "string" && j.text.length ? j.text : null;
  } finally {
    clearTimeout(t);
  }
}

export async function brainHealth(env, timeoutMs = 8000) {
  if (!env.BRAIN_URL || !env.BRAIN_TOKEN) return { ok: false, reason: "not-configured" };
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(String(env.BRAIN_URL).replace(/\/$/, "") + "/health", {
      signal: ctl.signal,
      headers: { "authorization": "Bearer " + env.BRAIN_TOKEN },
    });
    if (!r.ok) return { ok: false, reason: "http-" + r.status };
    return { ok: true, ...(await r.json()) };
  } catch (e) {
    return { ok: false, reason: String((e && e.name) || e).slice(0, 80) };
  } finally {
    clearTimeout(t);
  }
}
