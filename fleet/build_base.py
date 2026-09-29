#!/usr/bin/env python3
"""Build the fleet training dataset base.

Reads manifest.json: { agent_id: {dataset, qcol, acol, tcol?, sample, license} }
For each entry:
  1. asks datasets-server for parquet URLs (curl, proxy-safe)
  2. downloads the first split's parquet (curl -L)
  3. samples N rows with pyarrow, maps columns -> title/body/tags
  4. inserts into the FTS5 docs table, records the source

Usage: python3 build_base.py [--manifest manifest.json] [--db base.db] [--agent tech-soc]
"""
import argparse, json, os, sqlite3, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
DS_API = "https://datasets-server.huggingface.co/parquet?dataset="

def curl_json(url):
    out = subprocess.run(["curl", "-sL", "--max-time", "60", url],
                         capture_output=True, text=True)
    out.check_returncode()
    return json.loads(out.stdout)

def download(url, dest):
    subprocess.run(["curl", "-sL", "--max-time", "600", "-o", dest, url],
                   check=True)

def first_parquet_url(dataset_id, spec):
    # manifest can pin an exact file (for repos whose layout datasets-server can't index)
    if spec.get("parquet_url"):
        return spec["parquet_url"], {"parquet_files": [{"url": spec["parquet_url"]}]}
    info = curl_json(DS_API + dataset_id)
    files = info.get("parquet_files") or []
    if not files:
        raise RuntimeError(f"no parquet files listed for {dataset_id}")
    return files[0]["url"], info

Q_CANDIDATES = ["question", "instruction", "user", "input", "prompt", "query", "name"]
A_CANDIDATES = ["answer", "completion", "assistant", "output", "response", "body", "text", "context", "description_en", "description"]

def autodetect(names):
    q = next((c for c in Q_CANDIDATES if c in names), None)
    a = next((c for c in A_CANDIDATES if c in names), None)
    if not q or not a:
        raise RuntimeError(f"cannot autodetect Q/A columns; have {sorted(names)}")
    return q, a

def parse_conversations(table, spec):
    """Flatten a [{from: human|gpt, value: ...}] column into (question, answer) pairs."""
    names = set(table.schema.names)
    ccol = spec.get("conversations_col", "conversations")
    if ccol not in names:
        raise RuntimeError(f"conversations column {ccol!r} missing; have {sorted(names)}")
    filt = (spec.get("filter") or "").lower()
    pairs = []
    for conv in table.column(ccol).to_pylist():
        if not conv:
            continue
        # normalize to list of (role, text)
        turns = []
        for t in conv:
            if isinstance(t, dict):
                turns.append((str(t.get("from", "")).lower(), str(t.get("value", ""))))
            elif isinstance(t, (list, tuple)) and len(t) >= 2:
                turns.append((str(t[0]).lower(), str(t[1])))
        for i in range(len(turns) - 1):
            role, text = turns[i]
            nrole, ntext = turns[i + 1]
            if role == "human" and nrole == "gpt" and text.strip() and ntext.strip():
                if filt and filt not in text.lower() and filt not in ntext.lower()[:400]:
                    continue
                pairs.append((text.strip(), ntext.strip()))
    return pairs

def ingest(agent_id, spec, db_path, tmpdir):
    import pyarrow.parquet as pq
    dataset_id = spec["dataset"]
    sample = int(spec.get("sample", 40))
    print(f"[{agent_id}] {dataset_id} ...", flush=True)
    url, info = first_parquet_url(dataset_id, spec)
    pf = os.path.join(tmpdir, agent_id.replace("/", "_") + ".parquet")
    download(url, pf)
    if os.path.getsize(pf) < 4 or open(pf, "rb").read(4) != b"PAR1":
        raise RuntimeError(f"bad parquet magic for {dataset_id}")
    table = pq.read_table(pf)
    names = set(table.schema.names)
    candidates = []  # (question, answer, tag)
    if spec.get("conversations"):
        for q, a in parse_conversations(table, spec):
            candidates.append((q, a, ""))
    else:
        qcol = spec.get("qcol") or autodetect(names)[0]
        acol = spec.get("acol") or autodetect(names)[1]
        tcol = spec.get("tcol")
        for c in (qcol, acol):
            if c not in names:
                raise RuntimeError(f"{dataset_id}: column {c!r} missing; have {sorted(names)[:12]}")
        qvals = table.column(qcol).to_pylist()
        avals = table.column(acol).to_pylist()
        tvals = table.column(tcol).to_pylist() if tcol and tcol in names else [None] * table.num_rows
        # filter the WHOLE table for usable rows first, then sample —
        # some datasets only have Q&A on a subset of rows
        for i in range(table.num_rows):
            q, a = qvals[i], avals[i]
            if q is None or a is None:
                continue
            q, a = str(q).strip(), str(a).strip()
            if not q or not a:
                continue
            tags = str(tvals[i]).strip() if tvals[i] else ""
            candidates.append((q, a, tags))
            if len(candidates) >= sample:
                break
    rows = [(agent_id, dataset_id, q[:500], a[:4000], t[:300])
            for q, a, t in candidates[:sample]]
    con = sqlite3.connect(db_path)
    con.execute("DELETE FROM docs WHERE agent_id = ?", (agent_id,))
    con.executemany(
        "INSERT INTO docs (agent_id, dataset_id, title, body, tags) VALUES (?,?,?,?,?)",
        rows)
    colinfo = ({"conversations": True, "filter": spec.get("filter")}
               if spec.get("conversations")
               else {"q": spec.get("qcol"), "a": spec.get("acol"), "t": spec.get("tcol")})
    con.execute(
        """INSERT INTO sources (agent_id, dataset_id, license, rows_total, rows_used, columns)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(agent_id) DO UPDATE SET
             dataset_id=excluded.dataset_id, license=excluded.license,
             rows_total=excluded.rows_total, rows_used=excluded.rows_used,
             columns=excluded.columns, ingested_at=datetime('now')""",
        (agent_id, dataset_id, spec.get("license", ""),
         table.num_rows, len(rows), json.dumps(colinfo)))
    con.commit()
    con.close()
    os.remove(pf)
    print(f"[{agent_id}] ingested {len(rows)}/{table.num_rows} rows", flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=os.path.join(BASE, "manifest.json"))
    ap.add_argument("--db", default=os.path.join(BASE, "base.db"))
    ap.add_argument("--agent", default=None)
    args = ap.parse_args()
    if not os.path.exists(os.path.join(BASE, "schema.sql")):
        sys.exit("schema.sql missing")
    con = sqlite3.connect(args.db)
    con.executescript(open(os.path.join(BASE, "schema.sql")).read())
    con.close()
    manifest = json.load(open(args.manifest))
    if args.agent:
        manifest = {args.agent: manifest[args.agent]}
    with tempfile.TemporaryDirectory() as tmpdir:
        for agent_id, spec in manifest.items():
            try:
                ingest(agent_id, spec, args.db, tmpdir)
            except Exception as e:
                print(f"[{agent_id}] FAILED: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    main()
