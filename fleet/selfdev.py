#!/usr/bin/env python3
"""Autonomous self-development loop for the 30 tech workers.

Each worker uses the local ONNX model to build itself:
  1. pulls its current memory via o22ugdw213-web /api/memory
  2. pulls its domain slice from the query-tunnel dataset base
  3. finds domain knowledge NOT already covered in its memory
  4. synthesizes new Q&A entries with the model (few-shot, greedy)
  5. writes them back to its own memory (unless --dry-run)

Workers with no dataset slice elaborate from their existing memory instead,
so all 30 agents self-develop every run.

Budget: --per-agent N (default 3) -> ~90 KV puts per full run, well under
the 1,000/day free cap.

Usage:
  python3 selfdev.py --dry-run [--agent tech-soc] [--per-agent 3]
  python3 selfdev.py --live    # actually writes to agent memories
"""
import argparse, datetime, json, os, re, sqlite3, sys, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://o22ugdw213.network"
MODEL_DIR = os.path.join(BASE, "models", "distilgpt2")
TOKEN_FILE = os.path.expanduser("~/.config/ibot/fleet_token")

# ---------------------------------------------------------------- site API
def site_token():
    return open(TOKEN_FILE).read().strip()

def api(path, method="GET", body=None, retries=2):
    req = urllib.request.Request(
        SITE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {site_token()}",
                 "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) fleet-selfdev/1.0"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if attempt < retries:
                continue
            print(f"  api {method} {path} failed: {e}", flush=True)
            return {}
    return {}

def get_memory(agent):
    # the workers' /memory has no list-all; enumerate via broad searches
    seen = {}
    for term in ("the", "a", "and", "to", "of", "is"):
        d = api(f"/api/memory?agent={agent}&search={term}")
        for it in d.get("results") or d.get("entries") or []:
            if isinstance(it, dict):
                key = it.get("key", "")
                if key not in seen:
                    seen[key] = it.get("text") or it.get("value") or ""
    return [{"key": k, "text": v} for k, v in seen.items()]

def put_memory(agent, key, text, tags):
    return api("/api/memory", "POST",
               {"agent": agent, "key": key, "text": text, "tags": tags})

# ---------------------------------------------------------------- dataset slice
def domain_rows(agent):
    db = os.path.join(BASE, "base.db")
    if not os.path.exists(db):
        return []
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT title, body FROM docs WHERE agent_id = ?", (agent,)).fetchall()
    con.close()
    return [dict(r) for r in rows]

# ---------------------------------------------------------------- model
_model = None

def load_model():
    global _model
    if _model is not None:
        return _model
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(os.path.join(MODEL_DIR, "tokenizer.json"))
    sess = ort.InferenceSession(
        os.path.join(MODEL_DIR, "model_quantized.onnx"),
        providers=["CPUExecutionProvider"])
    in_names = [i.name for i in sess.get_inputs()]
    has_cache = any("past" in n for n in in_names)
    _model = {"tok": tok, "sess": sess, "np": np,
              "in_names": in_names, "has_cache": has_cache}
    print(f"model loaded (cache={has_cache}, inputs={len(in_names)})", flush=True)
    return _model

FEWSHOT = ("From the statement, write one question and answer it using ONLY "
           "words from the statement.\n\n"
           "Statement: Windows Event ID 4624 indicates a successful logon.\n"
           "Q: What does Windows Event ID 4624 indicate?\n"
           "A: a successful logon\n\n"
           "Statement: {stmt}\nQ:")

STOP = set(("what which when where who whom whose why how is are was were be "
            "been being do does did have has had the a an of to in on for with "
            "as by at from or and not it its this that these those you your we "
            "our they their he she him her can could should would may might "
            "will shall must".split()))

def grounded(answer, source, need=0.8):
    """Answer is only trustworthy if built from the source's own words."""
    aw = [w for w in re.findall(r"[a-z0-9]{2,}", answer.lower()) if w not in STOP]
    if not aw:
        return False
    sw = set(re.findall(r"[a-z0-9]{2,}", source.lower()))
    return sum(1 for w in aw if w in sw) / len(aw) >= need

def generate(prompt, max_new=70):
    m = load_model()
    np, tok, sess = m["np"], m["tok"], m["sess"]
    in_names = m["in_names"]
    out_names = [o.name for o in sess.get_outputs()]
    # map past inputs by layer: past_key_values.{l}.{key|value}
    n_layers = max(int(re.match(r".*\.(\d+)\.", n).group(1)) + 1
                   for n in in_names if "past" in n)
    past_names = [[next(n for n in in_names
                        if f".{l}.key" in n or f"_{l}_key" in n),
                   next(n for n in in_names
                        if f".{l}.value" in n or f"_{l}_value" in n)]
                  for l in range(n_layers)]
    has_pos = "position_ids" in in_names
    ids = tok.encode(prompt).ids
    prompt_len = len(ids)
    # GPT-2 dims for distilgpt2: 12 heads, head dim 64
    def empty_past(seqlen):
        return [np.zeros((1, 12, seqlen, 64), dtype=np.float32)
                for _ in range(n_layers * 2)]
    past = empty_past(0)  # nothing cached before the first step
    out_ids = []
    for step in range(max_new):
        if step == 0:
            step_ids, step_len = ids, prompt_len
        else:
            step_ids, step_len = [ids[-1]], 1
        feed = {"input_ids": np.array([step_ids], dtype=np.int64),
                "attention_mask": np.array([[1] * len(ids)], dtype=np.int64)}
        if has_pos:
            feed["position_ids"] = np.array(
                [list(range(len(ids) - step_len, len(ids)))], dtype=np.int64)
        # past always fed: this export requires it, zeros on first step
        for l in range(n_layers):
            feed[past_names[l][0]] = past[l * 2]
            feed[past_names[l][1]] = past[l * 2 + 1]
        outs = sess.run(out_names, feed)
        logits = outs[0][0, -1]
        # rebuild past from outputs (skip logits), matching by layer order
        present = outs[1:]
        new_past = []
        for l in range(n_layers):
            new_past.append(present[l * 2])
            new_past.append(present[l * 2 + 1])
        past = new_past
        nxt = int(np.argmax(logits))
        ids.append(nxt)
        out_ids.append(nxt)
        if nxt == tok.token_to_id("<|endoftext|>"):
            break
    return tok.decode(out_ids).strip()

def synth_qa(statement):
    raw = generate(FEWSHOT.format(stmt=statement[:600]), max_new=70)
    # expect "....? \nA: ...." — be lenient
    q, a = "", ""
    if "A:" in raw:
        q, a = raw.split("A:", 1)
    else:
        q = raw
    q = re.sub(r"^Q:\s*", "", q.strip().split("\n")[0])[:300]
    a = a.strip().split("\n")[0][:800]
    if len(q) < 12 or len(a) < 8:
        return None
    if not grounded(a, statement):
        return None  # model invented words outside the source — discard
    return q, a

# ---------------------------------------------------------------- dedupe
def tokens(s):
    return set(re.findall(r"[a-z0-9]{3,}", s.lower()))

def covered(text, existing_token_sets, thresh=0.6):
    ts = tokens(text)
    if not ts:
        return True
    for es in existing_token_sets:
        if not es:
            continue
        if len(ts & es) / max(len(ts), 1) >= thresh:
            return True
    return False

# ---------------------------------------------------------------- main loop
def develop(agent, per_agent, dry_run):
    print(f"[{agent}]", flush=True)
    mem = get_memory(agent)
    mem_sets = [tokens(m["text"]) for m in mem]
    print(f"  memory: {len(mem)} entries", flush=True)
    rows = domain_rows(agent)
    print(f"  dataset slice: {len(rows)} rows", flush=True)
    made = 0
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d")
    tried = 0
    for row in rows:
        if made >= per_agent:
            break
        tried += 1
        if tried > per_agent * 6:  # don't burn time on a saturated agent
            break
        seed = (row["title"] + " " + row["body"])[:700]
        if covered(seed, mem_sets):
            continue
        qa = synth_qa(seed)
        if not qa:
            continue
        q, a = qa
        text = f"Q: {q}\nA: {a}"
        if covered(text, mem_sets):
            continue
        key = f"selfdev-{stamp}-{made}"
        if dry_run:
            print(f"  [dry] {key}: Q: {q[:80]}", flush=True)
        else:
            r = put_memory(agent, key, text, ["selfdev", "synthetic"])
            if not r.get("ok", True):
                print(f"  write failed: {r}", flush=True)
                continue
            print(f"  wrote {key}", flush=True)
        mem_sets.append(tokens(text))
        made += 1
    # fallback: elaborate from own memory when no dataset slice or nothing new
    if made == 0:
        print("  nothing new from dataset slice; elaborating from memory", flush=True)
        for m in mem[: per_agent * 2]:
            if made >= per_agent:
                break
            seed = m["text"][:700]
            if not seed.strip():
                continue
            qa = synth_qa("Related concept. " + seed)
            if not qa:
                continue
            q, a = qa
            text = f"Q: {q}\nA: {a}"
            if covered(text, mem_sets):
                continue
            key = f"selfdev-{stamp}-{made}"
            if dry_run:
                print(f"  [dry] {key}: Q: {q[:80]}", flush=True)
            else:
                r = put_memory(agent, key, text, ["selfdev", "synthetic"])
                if not r.get("ok", True):
                    continue
                print(f"  wrote {key}", flush=True)
            mem_sets.append(tokens(text))
            made += 1
    print(f"[{agent}] done: {made} new entries", flush=True)
    return made

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="actually write to agent memories (default is dry-run)")
    ap.add_argument("--agent", default=None)
    ap.add_argument("--per-agent", type=int, default=3)
    args = ap.parse_args()
    manifest = json.load(open(os.path.join(BASE, "manifest.json")))
    agents = [args.agent] if args.agent else sorted(manifest.keys())
    # always include agents missing from the manifest so all 30 self-develop
    if not args.agent:
        try:
            d = api("/api/agents")
            roster = [w["id"] for w in d.get("fleet", [])]
            agents = sorted(set(agents) | set(roster))
        except Exception as e:
            print("roster fetch failed:", e, flush=True)
    dry = not args.live
    print(f"{'DRY-RUN' if dry else 'LIVE'}: {len(agents)} agents x {args.per_agent}", flush=True)
    total = 0
    for a in agents:
        try:
            total += develop(a, args.per_agent, dry)
        except Exception as e:
            print(f"[{a}] ERROR: {e}", flush=True)
    print(f"TOTAL new entries: {total}", flush=True)

if __name__ == "__main__":
    main()
