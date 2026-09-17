# Swarm Orchestration Learnings

Distilled 2026-09-17 from fable5-traces-sft (120), agentic-workflows-sft-100k
(150), multiagent-bidding-dialogue (40), crewai_finetuning_dataset (100).

## Trace shape

- Real coding-agent traces: ~26 messages, ~9 tool calls; the loop is
  assistant-acts → tool-responds → assistant-continues. Hard tasks hit 100+
  messages — budget context, summarize tool output.
- Tool results are terse status lines; parse as structured outcomes.

## Roles

- Role cards (goal + backstory + expertise) beat "helpful assistant" prompts;
  they anchor tool choice and output style. Re-inject on long traces — agents
  drift to generic behavior.
- Dev-swarm's 30 profiles should read as role cards, not capability lists.

## Coordination

- Queue (sqlite) with pull semantics; tasks idempotent (workers die mid-task).
- Top-3 FTS skill_context attached per task — agents act on retrieved
  knowledge, not prompt alone.
- Workers die silently (observed 30/30) — heartbeat checks before trust.
- Coordinator plans/decomposes; workers execute; no worker-spawned workers.
- Nested quoting in submit payloads hangs shells — keep payloads simple.

## Dialogue formats

- Debates need: shared topic, named agents with descriptions, full-generation
  turns, then a judge summary.
- Spec workflows as conversations first, DAGs second; keep a one-line context
  per workflow for retrieval.
