#!/usr/bin/env python3
"""Query tunnel: ask the dataset base, get ranked rows back.

Usage:
  python3 query.py --agent tech-soc "how to triage a phishing alert" [--n 5] [--db base.db]
  python3 query.py --list                       # agents + sources in the base
  python3 query.py --agent tech-soc --stats      # source info for one agent

BM25 over the FTS5 index, scoped to one agent (or --agent all).
Output is JSON: [{agent_id, dataset_id, title, body, tags, rank}].
"""
import argparse, json, os, sqlite3, sys

BASE = os.path.dirname(os.path.abspath(__file__))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(BASE, "base.db"))
    ap.add_argument("--agent", default=None)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("query", nargs="*")
    args = ap.parse_args()
    if not os.path.exists(args.db):
        sys.exit(f"db not found: {args.db} (run build_base.py first)")
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    if args.list:
        rows = con.execute(
            "SELECT agent_id, dataset_id, license, rows_used, ingested_at FROM sources ORDER BY agent_id"
        ).fetchall()
        print(json.dumps([dict(r) for r in rows], indent=1))
        return
    if args.stats:
        r = con.execute("SELECT * FROM sources WHERE agent_id = ?",
                        (args.agent,)).fetchone()
        print(json.dumps(dict(r) if r else {}, indent=1))
        return
    q = " ".join(args.query).strip()
    if not q or not args.agent:
        sys.exit("usage: query.py --agent <id|all> \"<question>\"")
    # FTS5 MATCH with OR-joined terms so BM25 ranks partial matches;
    # a phrase query would require all terms adjacent and return nothing.
    match = " OR ".join(f'"{t}"' for t in q.split())
    if args.agent == "all":
        sql = """SELECT agent_id, dataset_id, title, body, tags, rank
                 FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT ?"""
        params = (match, args.n)
    else:
        sql = """SELECT agent_id, dataset_id, title, body, tags, rank
                 FROM docs WHERE docs MATCH ? AND agent_id = ? ORDER BY rank LIMIT ?"""
        params = (match, args.agent, args.n)
    rows = con.execute(sql, params).fetchall()
    print(json.dumps([dict(r) for r in rows], indent=1))

if __name__ == "__main__":
    main()
