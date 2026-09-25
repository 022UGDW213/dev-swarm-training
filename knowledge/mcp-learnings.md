# MCP Protocol Learnings

Distilled 2026-09-17 from hf-mcp-server/test-mcp-logs (113), mcp-server-bench
(150), DeepNLP/mcp-servers catalog (108).

## Protocol

- Handshake: `initialize` with `protocolVersion` (e.g. 2025-06-18) +
  `capabilities` (`sampling`, `elicitation`) + `clientInfo`. Version mismatch
  is the first thing to check on misbehavior.
- Capabilities must be declared, never assumed; sessions end with
  `session_delete` — orphans mean the client isn't cleaning up.
- Elicitation needs a human in the loop; headless clients hang. Cap sampling
  recursion (server→LLM→tool→server loops).

## Auth

- 58/113 test sessions were unauthorized: gate *execution* on auth, not
  session creation. Log client name + IP on failures.
- Never expose privileged tools (e.g. a root `bash` tool) over the network
  without auth.

## Evaluation

- Load-test before trusting a server: virtual users, req/s, success rate,
  avg/p95/p99 latency. Size timeouts off p99 (long-tail on LLM-backed tools).
- Failed requests at 1 virtual user = broken server, not load.
- Transports: stdio for local servers, `http_api` / `mcp_streamable` for
  remote — the bench covers both (90 + 60 scenarios).

## Docs discipline

- Keep the SKILL.md tool list in sync with the actual server tools; drift
  causes agents to call nonexistent tools.
- Test-harness logs teach protocol shape, not real traffic — validate timeouts
  against your own logs.
