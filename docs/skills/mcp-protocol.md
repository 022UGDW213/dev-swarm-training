# MCP Protocol Skill

Runbook for Model Context Protocol work. Grounded in 371 HF docs:
`hf-mcp-server/test-mcp-logs` (113 real session logs),
`kshitijthakkar/mcp-server-bench` (150 load-test results),
`DeepNLP/mcp-servers` (108 server catalog entries).

## The handshake (from real session logs)

Every MCP session starts with `initialize`:

```json
{"protocolVersion": "2025-06-18",
 "capabilities": {"sampling": {}, "elicitation": {}},
 "clientInfo": {"name": "fast-agent-mcp", "version": "0.3.28"}}
```

- **protocolVersion is negotiated.** Log it; mismatches are the first thing to
  check when a client/server pair misbehaves.
- **Capabilities are explicit:** `sampling` (server may ask the client LLM for
  completions), `elicitation` (server may request user input). A server must
  not assume either — declare and check.
- Sessions end with `session_delete`. In this corpus the 113 log rows split
  77 `initialize` + 36 `session_delete` — most rows have no teardown at all, so
  if you see long-lived orphaned sessions in your own logs that is the first
  hygiene bug to chase. Verify:
  `sqlite3 data/index.db "select text from docs where dataset='hf-mcp-server/test-mcp-logs'" | grep -oE '^method=[a-z_]+' | sort | uniq -c` → `77 method=initialize`, `36 method=session_delete`.

## Auth

The logs carry an `authorized` boolean per session — 58/113 test sessions were
**unauthorized**. Design for this:

- Gate tool execution on the auth check, not on session creation. An
  unauthorized session can still handshake; it must not execute.
- Log auth failures with client name + IP (`::ffff:127.0.0.1` style) — the
  corpus shows this is how abuse gets spotted.

## What's in the ecosystem (catalog, 108 servers)

The 108 `DeepNLP/mcp-servers` catalog digests each carry a server name plus its
marketing/README text — e.g. `AgentRPC`, `Actors MCP Server` ("Use 3,000+
pre-built cloud tools to extract data from websites, e-commerce, social media,
search engines, maps, and more"). Note the catalog's own `subfield` column is
the literal string `MCP SERVER` for all 108 rows, so it carries no usable
taxonomy — read the description text instead. Verify:
`sqlite3 data/index.db "select text from docs where dataset='DeepNLP/mcp-servers'" | grep -c '\[MCP SERVER\]$'` → `108`.

When evaluating a server for a local stdio harness or an n8n wiring:

1. Check its declared tools and required capabilities.
2. Check its transport: the bench corpus covers `http_api` (90 scenarios) and
   `mcp_streamable` (60) — stdio suits local servers, streamable HTTP suits
   remote ones.
3. Load-test before trusting: the bench runs 1/10/25/50 virtual users against
   tools (`echo`, `fibonacci`, `json_transform`, `async_sleep`, `payload_echo`)
   on `gradio` (110 scenarios) and `fastmcp` (40) servers, and records request
   totals and success/failure counts per scenario.

## Load-test checklist (from mcp-server-bench)

Per scenario record the index actually holds: `scenario_id`, `server`,
`protocol`, `tool`, `virtual_users`, `duration_s`, `total_requests`,
`successful_requests`, `failed_requests` — plus `concurrency_limit` on 110 of
the 150.

**No latency field is present.** `train/ingest_ml_agents.py` asks each row for
`requests_per_second`, `avg_latency_ms`, `p95_latency_ms` and `p99_latency_ms`,
but the rows served by datasets-server carry none of them, so 0 of the 150
indexed records has a latency percentile. Verify:
`sqlite3 data/index.db "select count(*) from docs where dataset='kshitijthakkar/mcp-server-bench' and (text like '%p95%' or text like '%avg_latency%' or text like '%requests_per_second%')"` → `0`.

- **p95/p99, not avg is the right instinct** — MCP tool calls have long-tail
  latency (LLM-backed tools especially), so size timeouts off a percentile, not
  a mean. This corpus cannot supply that percentile: measure it on your own
  server before trusting a timeout budget.
- **Failure budget:** any `failed_requests > 0` at 1 virtual user means the
  server is broken, not loaded — fix before scaling users.
- **Concurrency limits:** 110 of the 150 scenarios set `concurrency_limit`;
  respect it or you'll benchmark the queue, not the server.

## Local stdio MCP server (host-side mapping)

This section was written against a local stdio MCP server (recorded
2026-09-17) that exposed `open_chrome`, `apt_install`, a root `bash`, and
`vm_status`. That server is **not present on the current workstation**
(`~/workspace/mcp-server/server.py` does not exist here — re-checked
2026-09-27), so treat its tool list as the worked example rather than as a live
inventory. The lessons apply to any local stdio server:

- One tool = one verb, JSON-schema params with `required` — same discipline
  as the LLM tool-calling skill.
- A root `bash` tool is the dangerous one: scope commands, log invocations,
  never expose it over the network without the auth lesson above.
- Keep the skill doc in sync with the tool list — drift between docs and tools
  is how agents call tools that don't exist.

## Pitfalls

- **Version drift:** client 0.3.28 vs server expecting another protocolVersion
  → silent capability mismatch. Pin and log versions on both ends.
- **Elicitation without UX:** if your server uses elicitation, the client must
  have a human in the loop — headless clients hang.
- **Sampling loops:** server asks client LLM → client calls server tool →
  server asks again. Cap recursion depth.
- **Test logs are not production traffic:** the 113 sessions come from one
  test server (every row logs `ip=::ffff:127.0.0.1`) and 10 client
  name+version pairs across `fast-agent-mcp` (0.3.8, 0.3.28, 0.4.1, 0.4.2,
  0.4.26, 0.4.28, 0.7.18), `inspector-client` (0.17.2, 0.17.4) and
  `claude-code` (1.0.62) — great for protocol shape, not for real-world traffic
  patterns. Verify:
  `sqlite3 data/index.db "select text from docs where dataset='hf-mcp-server/test-mcp-logs'" | grep -oE 'client=[^ ]+ v[0-9.]+' | sort -u | wc -l` → `10`.
  Validate against your own logs before tuning timeouts.
