# dev-swarm-training

Training knowledge for the [dev-swarm](https://github.com/022UGDW213) agent fleet:
**2,707 full-text-indexed documents** across ML, LLM, multi-agent swarm, and MCP
lanes, plus the skill runbooks distilled from them — and a **zero-dependency
Node.js module** (`index.js`) to query it all.

## What was trained

The shared FTS5 knowledge index grew **1,126 → 2,707 docs** (+1,581) in this
training pass. Each doc is a distilled per-row digest (a LoRA config, a tool
schema, an agent-trace role flow, an MCP session log) — not a raw data blob.

| Lane | Docs | Datasets ingested |
|---|---|---|
| `ml-training` | 150 | `odyn-network/lora-hyperparameter-benchmark-v1` (50) — verified LoRA configs: rank/alpha/dropout/lr/epochs/seq_len · `pgurazada1/machine-failure-mlops-demo-logs` (100) — MLOps telemetry + failure predictions |
| `llm-ops` | 650 | `NousResearch/hermes-function-calling-v1` (200) — tool schemas + dialogues · `glaiveai/glaive-function-calling-v2` (150) · `nvidia/Nemotron-RL-Agentic-Function-Calling-Pivot-v1` (150) — agentic trajectories · `stindardlogic/tool-calling-english-100k` (150) — parallel/multiturn tool calls |
| `swarm-multiagent` | 410 | `Swarm-AI-Research/fable5-traces-sft` (120) — multi-turn agent traces (~26 msgs, 9 tool calls avg) · `stindardlogic/agentic-workflows-sft-100k` (150) · `LangChainDatasets/multiagent-bidding-dialogue` (40) · `DrDrek/crewai_finetuning_dataset` (100) — agent role profiles |
| `mcp-protocol` | 371 | `hf-mcp-server/test-mcp-logs` (113) — real MCP handshakes (`initialize`, protocolVersion `2025-06-18`, sampling/elicitation) · `kshitijthakkar/mcp-server-bench` (150) — load tests, p95/p99 · `DeepNLP/mcp-servers` (108) — server catalog |

The bundled `data/index.db` snapshot (6.1 MB) holds the **full shared index**,
so it also includes the earlier lanes: `devops-01/16/27` (300 docs each) and
`design-web` (226). Skipped datasets (gated, image-only, or not served by
datasets-server) are recorded in `knowledge/manifest.json`.

## How the ingest works

`train/ingest_ml_agents.py` fetches parquet rows through the
[datasets-server](https://datasets-server.huggingface.co/parquet?dataset=<id>)
API with `curl` — the standard `huggingface_hub` client fails in this
environment because Python can't parse the egress proxy URL. Each dataset gets
a digest function (`doc_odyn`, `doc_hermes`, `doc_mcplogs`, …) that turns a raw
row into a compact text record, written to `knowledge/<lane>.jsonl`; the
shared FTS5 index (`agent_id`, `dataset`, `text`) is then rebuilt from all
JSONL files.

Rebuild the index from scratch:

```bash
npm run build-index   # python3 train/ingest_ml_agents.py
```

## The Node module

Zero runtime dependencies — it uses Node's built-in `node:sqlite` (needs
Node ≥ 23.4). No install step beyond cloning:

```js
import { searchKnowledge, listSkills, getSkill, stats } from 'dev-swarm-training';

stats();
// { total: 2707, lanes: { 'ml-training': 150, 'llm-ops': 650, ... } }

searchKnowledge('LoRA rank alpha', { lane: 'ml-training', limit: 3 });
// [{ lane: 'ml-training', dataset: 'odyn-network/lora-hyperparameter-benchmark-v1',
//    text: 'LORA FINE-TUNE CONFIG: ...', rank: -8.42 }, ...]

listSkills();            // ['llm-ops', 'mcp-protocol', 'ml-training', 'swarm-orchestration']
getSkill('mcp-protocol'); // full Markdown runbook
```

Run the smoke test:

```bash
npm install   # creates node_modules (empty — zero deps)
node example.js
```

### API

- `searchKnowledge(query, { lane?, limit? })` — FTS5 `MATCH` search (user input
  is safely quoted); `lane` restricts to one of the four training lanes.
- `stats()` — `{ total, lanes }` doc counts per lane.
- `listSkills()` — names of the bundled skill runbooks.
- `getSkill(name)` — a runbook's Markdown (throws on unknown name).
- `close()` — close the read-only DB handle (optional).

## Layout

```
index.js            # the Node module (zero deps)
example.js          # smoke test: stats, search, skills
package.json
data/index.db       # 6.1 MB FTS5 snapshot of the knowledge index
docs/skills/        # 4 skill runbooks (ml-training, llm-ops, swarm-orchestration, mcp-protocol)
knowledge/          # 4 learnings files + manifest.json (datasets, row counts, skips)
train/              # ingest_ml_agents.py — the dataset ingest + index builder
```

## Notes

- The index snapshot is a point-in-time copy; re-run the ingest to refresh it.
- Publishing to npm is left to the repo owner (`npm publish` needs their auth).
- MIT licensed.
