# Swarm Orchestration Learnings

Distilled 2026-09-17 from fable5-traces-sft (120), agentic-workflows-sft-100k
(150), multiagent-bidding-dialogue (40), crewai_finetuning_dataset (100).

## Trace shape

- Real coding-agent traces exist in the corpus but are the minority: of the 120
  indexed fable5 traces only **16 carry any tool call** — the other 104 are a
  single user→assistant exchange (2 messages, 0 tool calls). Over the whole 120
  the average is 25.9 messages and 8.6 tool calls per trace (median 2, max 813),
  so those averages are carried entirely by the 16. The loop they show is
  assistant-acts → tool-responds → assistant-continues. On those long traces,
  budget context and summarize tool output.
- Tool results are terse status lines; parse as structured outcomes.

## Roles

- Role cards (goal + backstory + expertise) beat "helpful assistant" prompts;
  they anchor tool choice and output style. Re-inject on long traces — agents
  drift to generic behavior.
- Map them onto the dev-swarm lanes this index carries (`devops-01`,
  `devops-16`, `devops-27`) — each lane should read as role cards, not
  capability lists.

## Coordination

- Queue (sqlite) with pull semantics; tasks idempotent (workers die mid-task).
- Top-3 FTS skill_context attached per task — agents act on retrieved
  knowledge, not prompt alone.
- Workers die silently — check heartbeats before trusting "alive".
- Coordinator plans/decomposes; workers execute; no worker-spawned workers.
- Nested quoting in submit payloads hangs shells — keep payloads simple.

## Dialogue formats

- Debates need: shared topic, named agents with descriptions, full-generation
  turns, then a judge summary.
- Spec workflows as conversations first, DAGs second; keep a one-line context
  per workflow for retrieval.
