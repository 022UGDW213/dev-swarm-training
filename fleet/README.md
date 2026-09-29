# Fleet training — datasets, models, autonomous self-development

Local indexed knowledge base + self-development loop for the 30 tech-* agents.

## Layout
- `schema.sql` — FTS5 `docs` table (agent_id, dataset_id, title, body, tags) + `sources` registry
- `build_base.py` — manifest-driven ingestion: Hugging Face datasets-server parquet -> sample -> FTS5 (no `huggingface_hub`, curl-based, proxy-safe)
- `query.py` — the query tunnel: BM25-ranked retrieval scoped per agent (or all)
- `selfdev.py` — autonomous self-development loop: each worker reads its own memory, finds knowledge gaps vs its dataset slice, synthesizes grounded Q&A with the local model, writes back to its own memory
- `manifest.json` — agent -> {dataset, qcol, acol, tcol?, sample, license}; 27/30 agents mapped (tech-backup + tech-performance have no suitable public HF dataset; tech-cicd needs a conversations parser)
- `base.db` — the built index (WAL mode), ~30-50 sampled rows per agent
- `models/distilgpt2/` — Xenova/distilgpt2 quantized ONNX (236 MB, **Git LFS**), tokenizer + configs; GPT-2 family, no Llama anywhere

## Usage
```bash
# ingest / rebuild the dataset base
python3 build_base.py
python3 build_base.py --agent tech-soc          # one agent only

# query tunnel
python3 query.py --agent tech-soc "how to triage a phishing alert" --n 5
python3 query.py --agent all "zero trust" --n 5
python3 query.py --list                          # agents + sources

# autonomous self-development (dry-run by default)
python3 selfdev.py --agent tech-forensics --per-agent 3
python3 selfdev.py --live --per-agent 3          # writes to agent memories
```

## How selfdev works
1. Pulls the worker's current memory via `o22ugdw213-web /api/memory`.
2. Compares against its Hugging Face dataset slice in `base.db`.
3. Finds domain knowledge not already covered (token-overlap dedupe).
4. Synthesizes new Q&A entries with the local ONNX model (few-shot, greedy, KV-cache).
5. **Grounding gate:** every content word of a generated answer must come from the source statement — ungrounded samples are discarded, never written.
6. Writes approved entries back to the worker's own memory (`--live`).

## Notes
- The `.onnx` model is stored with Git LFS (`fleet/models/**/*.onnx` in `.gitattributes`). Clone with a Git LFS-capable client or fetch it separately from `https://huggingface.co/Xenova/distilgpt2`.
- Dataset licenses are recorded per-agent in `manifest.json` (mit / apache-2.0 / cc-by-4.0 / cc0-1.0 / cc-by-sa-4.0). Nothing here redistributes full datasets — only small sampled excerpts used as private agent memory.
- Model files live outside the 100 MB GitHub single-file limit via LFS; `base.db` stays small because only samples are indexed.
