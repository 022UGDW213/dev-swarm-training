# dev-swarm-training

Training knowledge for the [dev-swarm](https://github.com/022UGDW213) agent fleet:
**3,295 full-text-indexed documents** across ML, LLM, multi-agent swarm, MCP,
and AI-tutoring lanes, plus the skill runbooks distilled from them — and a
**zero-dependency Node.js module** (`index.js`) to query it all.

## What was trained

`data/index.db` is a real SQLite **FTS5** index (`docs`, `docs_content`,
`docs_docsize`, `docs_idx`, `docs_data`, `docs_config`) holding **3,295**
documents across **9 lanes** (`agent_id` values), ingested from **27 Hugging
Face datasets**. Every lane count below is recorded in
`knowledge/manifest.json`, and the manifest's per-dataset row counts sum to
exactly 3,295 — the same number `SELECT count(*) FROM docs` returns.

How the index grew, read straight off the manifest's lane counts:

- earlier lanes — `devops-01` / `devops-16` / `devops-27` (300 docs each) +
  `design-web` (226) = **1,126**
- ML/LLM/swarm/MCP pass — 150 + 650 + 410 + 371 = **1,581**
- AI-tutoring pass — **588**

`1,126 + 1,581 + 588 = 3,295`. Of those three numbers only the total is
directly measurable from the shipped snapshot (that is the row count the
bundled `data/index.db` actually returns); the 1,126 and 2,707 waypoints are
the manifest's recorded lane counts, not states that were separately
snapshotted, so treat them as the ingest history rather than as current
measurements. Each doc is a distilled per-row digest (a LoRA config, a tool
schema, an agent-trace role flow, an MCP session log, a tutoring dialogue) —
not a raw data blob.

| Lane | Docs | Datasets ingested |
|---|---|---|
| `ml-training` | 150 | `odyn-network/lora-hyperparameter-benchmark-v1` (50) — verified LoRA configs: rank/alpha/dropout/lr/epochs/seq_len · `pgurazada1/machine-failure-mlops-demo-logs` (100) — MLOps telemetry + failure predictions |
| `llm-ops` | 650 | `NousResearch/hermes-function-calling-v1` (200) — tool schemas + dialogues · `glaiveai/glaive-function-calling-v2` (150) · `nvidia/Nemotron-RL-Agentic-Function-Calling-Pivot-v1` (150) — agentic trajectories · `stindardlogic/tool-calling-english-100k` (150) — parallel/multiturn tool calls (21/150 parallel, 16/150 multiturn) |
| `swarm-multiagent` | 410 | `Swarm-AI-Research/fable5-traces-sft` (120) — multi-turn agent traces (over the 120 indexed traces: avg 25.9 messages, 8.6 tool calls) · `stindardlogic/agentic-workflows-sft-100k` (150) · `LangChainDatasets/multiagent-bidding-dialogue` (40) · `DrDrek/crewai_finetuning_dataset` (100) — agent role profiles |
| `mcp-protocol` | 371 | `hf-mcp-server/test-mcp-logs` (113) — real MCP handshakes (`initialize`, protocolVersion `2025-06-18`, sampling/elicitation; 58/113 sessions unauthorized) · `kshitijthakkar/mcp-server-bench` (150) — load tests (90 `http_api` + 60 `mcp_streamable` scenarios), p95/p99 · `DeepNLP/mcp-servers` (108) — server catalog |
| `elearning-tutoring` | 588 | `princeton-nlp/TutorChat` (150) — tutor-student dialogues · `Eedi/Question-Anchored-Tutoring-Dialogues-2k` (138) — question-anchored dialogues; tutor talk moves counted in the 138 indexed dialogues: Press for Accuracy 603, Keep Together 368, Revoicing 186, Getting Student to Relate 16, Press for Reasoning 15, Restating 2 (1,190 labeled turns) · `knght0wl21/socratic-tutoring-dataset` (150) — socratic cases: question → incorrect solution → misconception probe · `derek-thomas/squad-v1.1-t5-question-generation` (150) — passage → quiz-question pairs |

The lanes that predate the ML/LLM/swarm/MCP pass (driven by an earlier ingest
script not present in this repo) are still carried in the bundle:
`devops-01` / `devops-16` / `devops-27` (300 docs each) and `design-web` (226).
Datasets skipped (gated, image-only, or not served by datasets-server) are
recorded in `knowledge/manifest.json` — 13 skipped dataset references on top of
the 27 that produced docs.

### Verified 2026-09-26 on this workstation

| Claim | Measured value | Command |
|---|---|---|
| bundle size | 8,749,056 bytes (8.7 MB decimal / 8.3 MiB) | `stat -c %s data/index.db` |
| document count | 3,295 | `python3 -c "import sqlite3;print(sqlite3.connect('file:data/index.db?mode=ro',uri=True).execute('select count(*) from docs').fetchone()[0])"` |
| FTS5 tables | `docs`, `docs_config`, `docs_content`, `docs_data`, `docs_docsize`, `docs_idx` | `sqlite_master` query |
| datasets ingested | 27 | `select count(distinct dataset) from docs` |
| lanes | 9 | `select agent_id, count(*) from docs group by agent_id` |
| manifest rows sum | 3,295 (equals the index count) | `python3 -c "import json;print(sum((v['docs'] if not isinstance(v['docs'],dict) else sum(v['docs'].values())) for v in json.load(open('knowledge/manifest.json')).values()))"` |
| smoke test | exit code 0, real hits | `node example.js` |

## How the ingest works

`train/ingest_ml_agents.py` fetches parquet rows through the
[datasets-server](https://datasets-server.huggingface.co/parquet?dataset=<id>)
API with `curl` — the standard `huggingface_hub` client fails in this
environment because Python can't parse the egress proxy URL. Each dataset gets
a digest function (`doc_odyn`, `doc_hermes`, `doc_mcplogs`, `doc_tutorchat`,
`doc_socratic`, …) that turns a raw row into a compact text record, written to
`knowledge/<lane>.jsonl`; the shared FTS5 index (`agent_id`, `dataset`,
`text`) is then rebuilt from all JSONL files. The tutoring lane has its own
script, `train/ingest_tutoring.py`, which groups Eedi's per-message rows into
dialogues by `InterventionId` and joins the `dq-question-metadata` anchor
question texts.

> **Known gap — re-ingest is not runnable from this snapshot.** Both
> `train/ingest_ml_agents.py` and `train/ingest_tutoring.py` import a shared
> helper module, `train/ingest.py` (`dataset_exists`, `fetch_rows`,
> `build_index`), which is **not in the repository** and was never committed
> (`git log --all -- train/ingest.py` is empty). `train/ingest_ml_agents.py`
> also cites `train/ingest_design.py` as the source of its transport pattern —
> that file is absent too. Running either script therefore fails immediately:
>
> ```
> $ python3 train/ingest_ml_agents.py
> ModuleNotFoundError: No module named 'ingest'      # exit code 1
> ```
>
> The bundled `data/index.db` is the finished artifact; rebuilding it needs
> those missing helpers (plus the `knowledge/*.jsonl` intermediates they
> produced, and network access to datasets-server). Until they are committed,
> treat the index as a point-in-time snapshot, not a reproducible build.

The rebuild entry point is:

```bash
npm run build-index   # python3 train/ingest_ml_agents.py && python3 train/ingest_tutoring.py
```

(Same caveat as above: it needs the missing `train/ingest.py`.)

## The Node module

Zero runtime dependencies — it uses Node's built-in `node:sqlite`. That module
is available without a flag from Node **v22.13.0 / v23.4.0** and is still
marked experimental on the v22/v23 lines, so the smoke test prints a
`ExperimentalWarning: SQLite is an experimental feature` line on stderr. The
run below was verified on **Node v22.23.2** (2026-09-26).

```js
import { searchKnowledge, listSkills, getSkill, stats } from 'dev-swarm-training';

stats();
// { total: 3295,
//   lanes: { 'design-web': 226, 'devops-01': 300, 'devops-16': 300, 'devops-27': 300,
//            'elearning-tutoring': 588, 'llm-ops': 650, 'mcp-protocol': 371,
//            'ml-training': 150, 'swarm-multiagent': 410 } }

searchKnowledge('LoRA rank alpha', { lane: 'ml-training', limit: 3 });
// [{ lane: 'ml-training', dataset: 'odyn-network/lora-hyperparameter-benchmark-v1',
//    text: 'LORA FINE-TUNE CONFIG:\nid=unsloth-default, ...', rank: -18.830656885425448 }, ...]

listSkills();            // ['ai-tutoring', 'llm-ops', 'mcp-protocol', 'ml-training', 'swarm-orchestration']
getSkill('mcp-protocol'); // full Markdown runbook
```

Query terms are ANDed as quoted FTS5 tokens — `searchKnowledge('MCP initialize')`
matches (112 docs); `searchKnowledge('MCP handshake initialize')` matches nothing,
because no indexed document contains the literal word `handshake`.

Run the smoke test (there are no dependencies, so no `npm install` is needed —
npm creates no `node_modules/` here):

```bash
node example.js   # or: npm test
```

### API

- `searchKnowledge(query, { lane?, limit? })` — FTS5 `MATCH` search (user input
  is safely quoted); `lane` restricts to one of the five training lanes
  (`ml-training`, `llm-ops`, `swarm-multiagent`, `mcp-protocol`,
  `elearning-tutoring`).
- `stats()` — `{ total, lanes }` doc counts per lane.
- `listSkills()` — names of the bundled skill runbooks.
- `getSkill(name)` — a runbook's Markdown (throws on unknown name).
- `close()` — close the read-only DB handle (optional).

## Layout

```
index.js                 # the Node module (zero deps)
example.js               # smoke test: stats, search, skills
package.json
data/index.db            # 8,749,056-byte FTS5 snapshot of the knowledge index
docs/skills/             # 5 skill runbooks (ai-tutoring, llm-ops, mcp-protocol,
                         #   ml-training, swarm-orchestration)
knowledge/               # 5 learnings files + manifest.json (lanes, datasets,
                         #   row counts, skips)
train/                   # ingest_ml_agents.py + ingest_tutoring.py (the index
                         #   builders; both import a missing train/ingest.py)
```

## Notes

- The index snapshot is a point-in-time copy; re-running the ingest would
  refresh it, but see the known gap above.
- Publishing to npm is left to the repo owner (`npm publish` needs their auth).
- MIT licensed.
