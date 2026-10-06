# backend/src/younique/agents/AGENTS.md

Rules for the LangGraph runtime. The root and `backend/` files apply too. Design:
`docs/03-designs/agent-runtime.md` and `docs/03-designs/safety-and-prompt-injection.md`.

## One runtime

Chat turns, background agents, and pipelines all execute here. Pipelines compile to
`StateGraph` objects; they do not have their own executor. If you find yourself writing a second
loop that calls tools, stop — you are duplicating this.

## State

`AgentState` in `state.py`. Rules about it:

- **Add a field only if it must survive a checkpoint.** State is serialized on every node
  boundary; it is not a scratchpad. Node-local data goes in `state["scratch"]`, which is never
  sent to the model.
- **`trust_level` only ever goes `trusted` → `untrusted`.** There is no code path that clears
  it. Do not add one. There is no reliable sanitizer for natural language, and a "sanitize"
  function would be a false security guarantee.
- **`principal_snapshot` is captured at run start and is the ceiling.** Re-validate against
  live state at every tool call; live state can only *narrow*. A permission granted mid-run
  never widens a run in flight.
- **`budget` lives in state** so a resumed run cannot forget what it already spent. Never read
  spend from a side table per step.
- Everything in state must be JSON-serializable. No ORM objects, no open file handles, no
  clients.

## Nodes

One responsibility each, in `nodes/`.

| Node | Must |
| --- | --- |
| `initialize` | Resolve model, tools, connections, memory sets; snapshot the principal; preflight the budget |
| `retrieve_memory` | Respect the token budget; never exceed `min(15% of window, 2000 tok)` |
| `pack_context` | Never orphan a `tool_result` from its `tool_call` — every provider hard-400s on that, and it is the most common bug in hand-rolled agent loops |
| `call_model` | Stream, retry per the error policy, fall back only on the permitted error kinds, persist partial output on interruption |
| `policy_gate` | Check allowlist, then `tool_policies`, then taint rules. In that order. |
| `execute_tools` | Run in parallel with a per-tool timeout; never swallow an exception |
| `observe` | **The only place tool output enters the conversation.** Taint, redact secrets, register artifacts, persist `run_steps` and I/O refs. |
| `write_memory` | Enqueue async extraction; never block the turn |
| `finalize` | Usage ledger, status, outbox event |

`observe` being the single ingress point is what makes tainting and redaction auditable. Do not
add a second path by which tool output reaches `state["messages"]`.

## Tool gating — the security core

```
allowlist  →  tool_policies  →  taint rules  →  live permission re-check  →  execute
```

Non-negotiable:

- A tool not in `tool_allowlist` is **refused before anything else**.
- `always_allow` does **not** survive tainting for a `medium` or `high` risk tool unless the
  user explicitly set `allow_when_tainted = true` on that tool. Do not add a bypass.
- A denied tool is **reported back to the model as a tool result**, not raised as an error. The
  model then explains the limitation to the user or picks a permitted alternative, which is far
  better than an error page.
- Tool output can never modify `tool_allowlist`, `tool_policies`, `budget`, or `trust_level`
  toward trust. There must be no code path from tool content to those fields — a reviewer should
  be able to verify this by reading `observe`.

## Approvals

- `interrupt()` suspends durably. The Cloud Run request **completes** and the instance is
  released. Never poll or sleep waiting for a human.
- Every `high` risk tool must implement `summarize_for_approval()`. A dialog showing raw JSON
  trains users to click through, which defeats the entire mechanism.
- Redact tool arguments through the secret patterns before persisting them to `approvals` —
  those rows are long-lived and widely readable within a workspace.
- Resume with `Command(resume=decision)` from a fresh Cloud Task. Never resume inline from the
  approval request.

## Checkpointing

- `AsyncPostgresSaver`, `thread_id = str(run_id)`, in the `langgraph` schema.
- **Alembic must never touch that schema.** Creating a migration against those tables corrupts
  live suspended runs.
- Upgrading `langgraph-checkpoint-postgres` is a schema change: release note plus a pre-deploy
  check that no runs are `awaiting_approval` if the checkpoint format changed.

## Limits

Enforced in `route` and `initialize`, never left to the model's judgement: 25 steps, 50 tool
calls, 30/60 min wall clock, remaining budget, sub-agent depth 3, 256 KB inline tool output.

A run that hits a limit fails with a **specific error and a remediation**. "This agent reached
its 25-step limit — raise it in settings or simplify the task" is actionable; "run failed" is
not.

## Sub-agents

- Tool allowlist is the **intersection** with the parent's. Never a union.
- Budget is a **slice** of the parent's, deducted from it.
- Taint is inherited down and propagates back up. Delegation is not a laundering mechanism.
- Own `run_steps` with `kind='subagent'` and `parent_run_step_id` so the UI renders the call
  tree.

## Testing

`FakeChatModel` with scripted responses. **No real model calls, ever, in any test here.**

Every change to gating, limits, or taint needs a test. The regression tests in
`tests/agents/test_injection.py` are the highest-value tests in the repository — add to them
whenever a new injection technique appears, and never weaken one to make a feature pass.

Agent *quality* (does it choose the right tool, is the answer good) is **not** tested here. That
is the nightly eval harness. Putting nondeterministic quality checks in CI makes the suite flaky
and contributors start ignoring red builds, which costs more than the tests are worth.
