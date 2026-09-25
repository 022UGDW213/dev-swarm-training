# LLM Ops Learnings

Distilled 2026-09-17 from hermes-function-calling-v1 (200), glaive-function-calling-v2
(150), Nemotron-RL-Agentic-Function-Calling-Pivot-v1 (150),
tool-calling-english-100k (150).

## Tool design

- Tool descriptions are the selection mechanism — vague descriptions cause
  wrong-tool calls more than any other factor.
- Verbs for names (`get_weather`, `create_calendar_event`); 2–5 tools per call,
  route first if you have dozens.
- JSON schema with typed params + `required` is the universal shape.

## Dialogue mechanics

- Give the model an explicit no-tool path (`no_tool_needed`); otherwise it
  force-fits tools onto chit-chat.
- Forbid assumed argument values in the system prompt (Hermes pattern).
- Multi-turn = loop model → tool → model; budget context for it.
- Parallel calls (21/150 = 14% of the ingested tool-calling sample) halve
  fan-out latency — enable when tools are independent.
- Cap tool rounds (~5); confused models loop forever.

## Agent honesty (Nemotron)

- The correct action when no tool covers the request is an explicit limitation
  statement naming the closest available tool — never a hallucinated result.
- Refusals ("I don't have that capability") are features — 12 glaive digests
  carry that exact refusal line.
- After each tool result, re-read the user request before the final answer.

## Portability

- Keep schemas OpenAI-compatible (`function.name`/`arguments`) — local
  (Ollama/Qwen) and hosted models both accept that shape.
