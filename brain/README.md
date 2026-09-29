# brain.cpp — local offline coding-model server

All fleet model inference goes through brain.cpp. No Llama anywhere:
models are Qwen2.5-Coder, served with onnxruntime (this server) or the
native brain.cpp binary on ibot-si.

## Layout

- `server.py` — the HTTP server. stdlib only + `optimum[onnxruntime]`.
  API: `GET /health`, `GET /models`, `POST /predict`, `POST /copilot`,
  `POST /command`. Every route needs `Authorization: Bearer $BRAIN_TOKEN`.
  Bodies capped at 256 KB. Listens on 9008 by convention (9009 = second instance).
- `config.json` — model registry. `backend: onnx` models are served by
  `server.py`; `engine: native` GGUF entries are served by the native
  brain.cpp binary on ibot-si and listed here so workers can address them.
- `worker-client.js` — `brainPredict` / `brainHealth` for the Cloudflare
  fleet workers. The `/model` relay tries brain.cpp first when
  `BRAIN_ENABLED=1`, and falls back to ibot-vault on any failure.
- `models/` — Git LFS. `qwen25-coder-0.5b-onnx` is the verification model
  (small enough to run anywhere, proves the full path end to end).
  The 3B and 7B GGUFs are staged for ibot-si.

## Run it

```bash
export BRAIN_TOKEN="$(openssl rand -hex 32)"   # never commit this
pip install --user --break-system-packages "optimum[onnxruntime]"
python3 brain/server.py
```

Verify:

```bash
curl -H "Authorization: Bearer $BRAIN_TOKEN" localhost:9008/health
curl -s -H "Authorization: Bearer $BRAIN_TOKEN" \
     -H 'content-type: application/json' \
     -d '{"prompt":"def fibonacci(n):","max_tokens":64}' \
     localhost:9008/predict
```

## Current status (2026-09-29)

- `server.py` + 0.5B ONNX verified working on the build VM (real inference,
  see test below). 3B/7B GGUFs are on disk, staged for ibot-si.
- ibot-si (native brain.cpp, :9008/:9009) is offline — fleet workers keep
  `BRAIN_ENABLED` off and use ibot-vault until it returns.

## Test log

Real generation through this server (0.5B Q4 ONNX, CPU):

> prompt: `def fibonacci(n):`
> → completes with a correct iterative fibonacci implementation
> (output captured at verification time; re-run the curl above to reproduce)
