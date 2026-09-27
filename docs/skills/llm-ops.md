# LLM Ops Skill — Function/Tool Calling

Runbook for wiring LLMs to tools. Grounded in 650 HF docs:
`NousResearch/hermes-function-calling-v1` (200), `glaiveai/glaive-function-calling-v2`
(150), `nvidia/Nemotron-RL-Agentic-Function-Calling-Pivot-v1` (150),
`stindardlogic/tool-calling-english-100k` (150).

## Tool schema design (the part that matters most)

Every schema-bearing example follows this shape — name, plain-language
description, typed parameters with `required`. 150 of the 650 ingest digests
embed a full schema like this (`required` + `properties`); the rest name tools
without carrying the schema text. Verify:
`sqlite3 data/index.db "select count(*) from docs where agent_id='llm-ops' and text like '%required%' and text like '%properties%'"` → `150`.

```json
{"name": "get_exchange_rate",
 "description": "Get the exchange rate between two currencies",
 "parameters": {"type": "object",
   "properties": {
     "base_currency": {"type": "string", "description": "The currency to convert from"},
     "target_currency": {"type": "string", "description": "The currency to convert to"}},
   "required": ["base_currency", "target_currency"]}}
```

- **Descriptions are load-bearing.** A tool description is the only text the
  model has to choose on, so write it as the instruction you want followed.
- **Name tools as verbs** (`get_weather`, `create_calendar_event`,
  `execute_python` — all from the 100k corpus). Noun names confuse selection.
- **Keep the tool list small per call.** Over the 200 Hermes examples the tool
  list per task runs 1–5 and never exceeds 5 (2–5 in 171 of 200; 1 in 29).
  If you have many tools, route first, then present the shortlist.
  Verify:
  `sqlite3 data/index.db "select text from docs where dataset='NousResearch/hermes-function-calling-v1'" | grep '^TOOLS: ' | awk -F', ' '{print NF}' | sort -n | uniq -c`.

## System-prompt patterns (two proven styles)

1. **Hermes style (XML tags):** "You are a function calling AI model. You are
   provided with function signatures within `<tools> </tools>` XML tags. You
   may call one or more functions… Don't make assumptions about what values
   to plug into functions." — explicit, works with chat templates.
2. **Glaive style (JSON in system):** "You are a helpful assistant with access
   to the following functions. Use them if required - {…schema…}". Simpler,
   single-turn oriented.

Both end with the same instruction: use tools when required, otherwise answer
directly.

## Call patterns from the corpora

- **Single vs multi-turn:** stindardlogic is mostly single-turn (only 16/150
  multiturn). For multi-step tasks, expect to loop: model → tool result →
  model, and budget context for it.
  Verify: `sqlite3 data/index.db "select text from docs where dataset='stindardlogic/tool-calling-english-100k'" | grep -c 'multiturn=True'` → `16`.
- **Parallel calls:** 21/150 stindard examples issue parallel tool calls — e.g.
  `TOOLS: get_stock_price, get_exchange_rate` with `parallel=True`. Enable
  parallel calling when tools are independent — it halves latency on fan-out
  tasks.
  Verify: `... | grep -c 'parallel=True'` → `21`.
- **`no_tool_needed`:** the corpus explicitly labels chit-chat where no tool
  should fire (11/150 rows carry `no_tool_needed=True`). Always give the model
  a clean "answer directly" path, or it will force-fit tools onto casual
  messages.
- **Refusals are features:** glaive examples show the assistant declining
  ("I'm sorry, but I don't have the capability to book flights") when no tool
  covers the request — 12 of the 150 ingested glaive rows carry that line.
  Verify: `sqlite3 data/index.db "select text from docs where dataset='glaiveai/glaive-function-calling-v2'" | grep -c "don't have the capability"` → `12`.
  A model that says "can't" beats one that hallucinates a booking.

## The Nemotron lesson (agentic trajectories)

The 150 NVIDIA agentic-trajectory digests record the corpus's own
`expected_action`: **81 `function_call` and 69 `message`** (verify:
`sqlite3 data/index.db "select text from docs where dataset='nvidia/Nemotron-RL-Agentic-Function-Calling-Pivot-v1'" | grep -oE 'EXPECTED ACTION \[[a-z_]+\]' | sort | uniq -c`).
Only **7 of those 69 messages** actually name a limitation of the available
tools — the rest are ordinary answers (summaries, arithmetic, comparisons).
So the corpus does not establish "when no tool fits, answer with a limitation
statement" as a rule; it shows a handful of clean examples of that behaviour,
which is the part worth copying:

1. Before acting, check: does any tool cover this request?
2. If no → say so, name the closest available tool, ask for clarification.
3. Never emit a confident answer synthesized from nothing.

Note the `LESSON:` line at the bottom of every Nemotron digest is the ingest
script's own annotation (`doc_nemotron` in `train/ingest_ml_agents.py`), not
text from the source dataset — the source supplies the numbers above, the
"never hallucinate a result" guidance is this repo's.

## Categories that work well (by corpus frequency)

The `stindardlogic` tool-call records are tagged by category and the ten most
frequent are travel (22), finance (15), calendar (12), weather (11),
database (11), navigation (9), translation (8), developer_tools (8),
productivity (7) and calculation (7) — verify with
`sqlite3 data/index.db "select text from docs where dataset='stindardlogic/tool-calling-english-100k'" | grep -oE 'TOOL-CALL RECORD \[[^]]*\]' | sort | uniq -c | sort -rn`.
The Hermes corpus uses its own taxonomy on top of that — `Model APIs` (23),
`E-commerce Platforms` (23), `IoT and Home Automation` (15),
`Communication Services Software` (37), `Financial Services Apps` (29).
If your domain is in either list, the index holds proven examples to mirror.

## Pitfalls

- **Assuming argument values:** Hermes's system prompt explicitly forbids it.
  Missing arg → ask the user or use a default, don't invent.
- **Tool-result blindness:** after a tool returns, re-read the original user
  request before composing the final answer — models drift.
- **Unbounded loops:** cap tool-call rounds (e.g. 5); a confused model will
  call tools forever without a budget.
- **Portability:** keep schemas OpenAI-compatible (`function.name` /
  `arguments`) — that is the shape local (Ollama/Qwen) and hosted models both
  accept, so the same tool definition travels.
