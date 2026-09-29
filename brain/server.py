#!/usr/bin/env python3
"""brain.cpp-compatible local inference server.

Serves local coding models over HTTP with the brain.cpp API surface
(ports 9008/9009, bearer-token auth). No Llama anywhere in the stack:
models are Qwen2.5-Coder served through onnxruntime.

API v1 (defined by this implementation):
  GET  /health                       -> {"ok": true, "model": "<default id>"}
  GET  /models                       -> {"models": [{"id", "backend", "status"}]}
  POST /predict  {prompt, max_tokens?, temperature?, stop?}
                                     -> {"text", "model", "tokens"}
  POST /copilot  {messages:[{role,content}], max_tokens?}
                                     -> {"choices": [{"message": {"role":"assistant","content"}}]}
  POST /command  {command: "status"|"reload", ...}
                                     -> {"result": ...}

Auth: every route requires  Authorization: Bearer <BRAIN_TOKEN>.
Request bodies are capped at 256 KB. Responses never include the token.
GGUF models listed in config.json with "engine": "native" are served by the
native brain.cpp binary (ibot-si); this server answers /models for them but
/predict returns 409 with an honest message instead of pretending.
"""
import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
BODY_LIMIT = 256 * 1024

_model = None
_model_lock = threading.Lock()
_tokenizer = None
_default_id = None
_registry = []


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_token():
    cfg = load_config()
    env_name = cfg.get("server", {}).get("token_env", "BRAIN_TOKEN")
    tok = os.environ.get(env_name, "")
    if not tok:
        print(f"WARNING: {env_name} is not set; all requests will 401", file=sys.stderr)
    return tok


def load_model():
    """Load the default ONNX model once, thread-safely. Raises loudly on failure."""
    global _model, _tokenizer, _default_id, _registry
    with _model_lock:
        if _model is not None:
            return
        from optimum.onnxruntime import ORTModelForCausalLM
        from transformers import AutoTokenizer

        cfg = load_config()
        _registry = cfg.get("models", [])
        onnx_models = [m for m in _registry if m.get("backend") == "onnx"]
        if not onnx_models:
            raise RuntimeError("config.json lists no backend=onnx model to serve")
        m = onnx_models[0] if not any(x.get("default") for x in onnx_models) else next(
            x for x in onnx_models if x.get("default")
        )
        _default_id = m["id"]
        model_dir = (HERE / m["path"]).resolve()
        file_name = m.get("file", "model.onnx")
        print(f"loading {_default_id} from {model_dir} ({file_name}) ...", flush=True)
        t0 = time.time()
        _tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=False)
        _model = ORTModelForCausalLM.from_pretrained(
            str(model_dir), file_name=file_name, trust_remote_code=False
        )
        print(f"model ready in {time.time()-t0:.1f}s", flush=True)


def generate(prompt, max_tokens=256, temperature=0.0, stop=None):
    load_model()
    max_tokens = max(1, min(int(max_tokens or 256), 1024))
    inputs = _tokenizer(prompt, return_tensors="pt")
    gen = dict(max_new_tokens=max_tokens, do_sample=False, pad_token_id=_tokenizer.eos_token_id)
    if temperature and float(temperature) > 0:
        gen.update(do_sample=True, temperature=float(temperature), top_p=0.95)
    with _model_lock:
        out = _model.generate(**inputs, **gen)
    text = _tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    if stop:
        for s in stop:
            if s in text:
                text = text.split(s)[0]
    return text, out[0].shape[1] - inputs["input_ids"].shape[1]


def native_only(model_id):
    return next((m for m in _registry if m["id"] == model_id and m.get("engine") == "native"), None)


class Handler(BaseHTTPRequestHandler):
    server_version = "brain.cpp/1.0"

    def log_message(self, *a):
        pass  # audit via /command status, not request logs

    def _auth(self):
        want = self.server.brain_token
        got = self.headers.get("authorization", "")
        if not want or not secrets.compare_digest(got, "Bearer " + want):
            self._send(401, {"error": "unauthorized"})
            return False
        return True

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        if n > BODY_LIMIT:
            return None
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode())
        except Exception:
            return None

    def do_GET(self):
        if not self._auth():
            return
        if self.path == "/health":
            load_model()
            self._send(200, {"ok": True, "model": _default_id})
        elif self.path == "/models":
            load_model()
            self._send(200, {"models": [
                {"id": m["id"], "backend": m["backend"],
                 "status": "native-only" if m.get("engine") == "native" else "ready"}
                for m in _registry
            ]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._auth():
            return
        data = self._body()
        if data is None:
            self._send(400, {"error": "bad json or body too large"})
            return
        if self.path == "/predict":
            prompt = data.get("prompt", "")
            if not prompt or not isinstance(prompt, str):
                self._send(400, {"error": "prompt is required"})
                return
            model_id = data.get("model")
            if model_id and native_only(model_id):
                self._send(409, {"error": f"model {model_id} is native-only; served by the brain.cpp binary on ibot-si, not this server"})
                return
            try:
                text, tokens = generate(prompt, data.get("max_tokens", 256),
                                        data.get("temperature", 0.0), data.get("stop"))
            except Exception as e:
                self._send(500, {"error": f"generation failed: {type(e).__name__}"})
                return
            self._send(200, {"text": text, "model": _default_id, "tokens": tokens})
        elif self.path == "/copilot":
            msgs = data.get("messages", [])
            try:
                prompt = _tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True) if _tokenizer else ""
            except Exception:
                prompt = "\n".join(m.get("content", "") for m in msgs)
            if not prompt:
                self._send(400, {"error": "messages is required"})
                return
            try:
                text, _ = generate(prompt, data.get("max_tokens", 256), data.get("temperature", 0.0))
            except Exception:
                self._send(500, {"error": "generation failed"})
                return
            self._send(200, {"choices": [{"message": {"role": "assistant", "content": text}}], "model": _default_id})
        elif self.path == "/command":
            cmd = data.get("command")
            if cmd == "status":
                load_model()
                self._send(200, {"result": {"ok": True, "model": _default_id,
                                            "registry": [m["id"] for m in _registry]}})
            elif cmd == "reload":
                global _model
                with _model_lock:
                    _model = None
                load_model()
                self._send(200, {"result": {"ok": True, "model": _default_id}})
            else:
                self._send(400, {"error": "unknown command"})
        else:
            self._send(404, {"error": "not found"})


def main():
    cfg = load_config()
    srv = cfg.get("server", {})
    host = srv.get("host", "127.0.0.1")
    port = int(srv.get("port", 9008))
    token = get_token()
    if not token:
        sys.exit(f"refusing to start without {srv.get('token_env', 'BRAIN_TOKEN')}")
    load_model()  # fail fast before binding
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.brain_token = token
    print(f"brain.cpp listening on {host}:{port} model={_default_id}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
