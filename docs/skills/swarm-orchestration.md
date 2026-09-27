# Swarm Orchestration Skill

Runbook for multi-agent work. Grounded in 410 HF docs:
`Swarm-AI-Research/fable5-traces-sft` (120 agent traces),
`stindardlogic/agentic-workflows-sft-100k` (150 workflow examples),
`LangChainDatasets/multiagent-bidding-dialogue` (40),
`DrDrek/crewai_finetuning_dataset` (100 role profiles).

## What real agent traces look like

The 120 indexed fable5 traces (`claude_code_session` origin) split into two very
different populations, measured 2026-09-27:

- **104 of the 120 are a single user → assistant exchange** — exactly 2 messages
  and 0 tool calls. These are not agent traces at all in the orchestration
  sense.
- **16 of the 120 are real multi-turn coding sessions** (≥1 tool call, role flow
  longer than 10 roles). These carry the whole average: **25.9 messages and 8.6
  tool calls per trace**, with the longest at 813 messages. The 16 are the part
  worth studying.

Verify:

```bash
D="select text from docs where dataset='Swarm-AI-Research/fable5-traces-sft'"
sqlite3 data/index.db "$D" | grep -oE 'TOOL CALLS: [0-9]+' | grep -c 'TOOL CALLS: 0'   # 104
sqlite3 data/index.db "$D" | grep -cE '^ROLE FLOW: user -> assistant$'                # 104
sqlite3 data/index.db "$D" | grep -oE '[0-9]+ messages' | cut -d' ' -f1 | sort -n \
  | awk '{a[NR]=$1; s+=$1} END{print "n="NR, "mean="s/NR, "median="a[int((NR+1)/2)], "max="a[NR]}'
# n=120 mean=25.9167 median=2 max=813
```

Over those 16 real traces the role flow has the shape

```
user → assistant → … → tool → assistant → tool → assistant …
```

- The loop is **assistant-acts → tool-responds → assistant-continues**. Design
  your orchestrator around this cycle, not around chat.
- Tool results are terse status lines ("File created successfully at …",
  "Exit code 1", "Command running in background with ID"). Parse them as
  structured outcomes, not prose.
- Long traces are the minority even here: only 8 of the 120 indexed rows run
  past 100 messages and the median row is 2. But that tail is where the context
  cost lives — when a trace does run long (up to 813 messages here), budget
  context for it and summarize tool output aggressively.

## Agent roles (from 100 CrewAI profiles)

Give each worker a **role card**: goal + backstory + expertise. The CrewAI
profiles look like this one (first row of `DrDrek/crewai_finetuning_dataset`,
stored verbatim — verify with
`sqlite3 data/index.db "select text from docs where dataset='DrDrek/crewai_finetuning_dataset' order by rowid limit 1"`):

> **Senior Research Analyst** — "goal is Uncover cutting-edge developments in AI
> and data science and backstory is You work at a leading tech think tank. Your
> expertise lies in identifying emerging trends. You have a knack for dissecting
> complex data and presenting actionable insights."

Role cards beat generic "you are a helpful assistant" because they anchor the
agent's tool choices and output style. Map them 1:1 onto the dev-swarm lanes
this index already carries (`devops-01`, `devops-16`, `devops-27` — 300 docs
each per `knowledge/manifest.json`) — each profile should read like a role
card, not a capability list.

## Workflow patterns (agentic-workflows-sft-100k)

- **Category your workflows** (`multi_agent_systems`, etc.) and keep a
  `context` line per workflow: one sentence on what the agents are
  orchestrating. Future you (and retrieval) will thank present you.
- **Conversation-first spec:** each workflow is defined by its dialogue, not
  by a DAG diagram. Write the expected agent exchange before the code.

## Multi-agent dialogue format (bidding/debate)

The bidding-dialogue corpus shows the setup that makes agent debates work —
though note the indexed snapshot is uneven: all 40 rows of
`LangChainDatasets/multiagent-bidding-dialogue` carry the `SETUP` block with the
topic and named agents, but only 10 of the 40 also carry a real full-generation
argument in `AGENT TURNS`. The other 30 store a single degenerate token
generation (29 as `<8>`-style, 1 as a bare `8`). Verify:

```bash
sqlite3 data/index.db "select text from docs where dataset='LangChainDatasets/multiagent-bidding-dialogue'" | grep -cE '^AGENT TURNS:'                       # 40
sqlite3 data/index.db "select text from docs where dataset='LangChainDatasets/multiagent-bidding-dialogue'" | grep -cE '"text": "<?[0-9]+>?"}'   # 30
```

1. **Topic** stated once, shared by all agents.
2. **Named agents with descriptions** ("Your name is X. Your description is…").
3. **Turns are full generations**, not one-liners — each agent argues its case
   (present in 10 of the 40 indexed rows).

Use this when agents must converge (design reviews, plan critiques): assign
positions, let them argue, then have a judge agent summarize.

## Orchestrator checklist (dev-swarm mapping)

Every bullet below was checked against the dev-swarm source (`swarm.py` in the
dev-swarm checkout, `dev-swarm/swarm.db` schema), not assumed:

- **Task queue over direct calls:** sqlite `tasks` table with
  `kind ∈ {shell, fetch, python}` — workers claim a row with
  `UPDATE tasks SET status='running', worker=? … WHERE id=(SELECT id FROM tasks WHERE status='pending' …)`,
  so they pull, never get pushed to. The queue outlives the workers.
- **Heartbeats:** the `workers` table carries `last_heartbeat`; a task left
  `running` longer than the staleness window is requeued to `pending`, and a
  dead worker often leaves no error behind. Check heartbeats before trusting
  "alive", restart dead ones.
- **skill_context per task:** an FTS5 query attaches the top-3 hits to each
  task's `skill_context` so every worker acts with retrieved knowledge, not
  just its prompt.
- **Idempotent tasks:** a worker may die mid-task; another picks it up. Tasks
  must be safe to retry.
- **Hung-task recovery:** nested quoting in submit payloads hangs shells —
  keep payloads simple; the CLI's `down` / `up` path (`down` requeues every
  `running` task back to `pending`) is the escape hatch when stuck.
- **One coordinator, N workers:** the coordinator plans and decomposes; workers
  execute. Workers do not spawn workers — the worker loop only claims `tasks`
  rows, and there is **no `max_depth` knob** anywhere in `swarm.py`; the
  constraint is structural (there is no spawn path), not a configurable depth.

## Pitfalls

- **No shared memory by default:** agents only know what the task payload and
  skill_context carry. Put state in the queue/DB, not in a worker's head.
- **Role drift:** without role cards, agents converge to generic assistant
  behavior within a few turns. Re-inject the role on long traces.
- **Tool-result flooding:** ~9 tool calls × verbose output = context death.
  Truncate tool output to what the next decision needs.
- **Silent death:** the failure mode to watch for is a worker that dies without
  leaving an error. Monitor, don't assume.
