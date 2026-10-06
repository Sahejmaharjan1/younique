# Architecture Decision Records

An ADR records *why* a decision was made, at the time it was made, with the alternatives that
were rejected. The design documents describe how the system works today; ADRs explain how it
came to be that way.

## Rules

1. **Immutable once accepted.** Never edit an accepted ADR except to change its status to
   `Superseded by ADR-NNNN`. The historical reasoning is the value — rewriting it destroys the
   record.
2. **One decision per file.** If you are writing "and also", it is two ADRs.
3. **Record the rejected options and why.** An ADR without alternatives is a changelog entry.
   The rejected options are what stop the same debate recurring in six months.
4. **Write one when a decision is hard to reverse, affects more than one area, or will
   surprise someone.** Not for routine choices.
5. **Number sequentially, never reuse a number**, even for an abandoned draft.

## Index

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-monorepo.md) | Single repository for all components | Accepted |
| [0002](0002-postgres-single-source-of-truth.md) | Postgres as the single source of truth | Accepted |
| [0003](0003-sse-for-streaming.md) | SSE over HTTP POST for chat streaming | Accepted |
| [0004](0004-cloud-tasks-and-pubsub.md) | Cloud Tasks for dispatch, Pub/Sub for events | Accepted |
| [0005](0005-db-backed-schedules.md) | One Cloud Scheduler job driving database-backed schedules | Accepted |
| [0006](0006-firebase-identity-only.md) | Firebase for identity only, with our own session layer | Accepted |
| [0007](0007-envelope-encryption-in-postgres.md) | Envelope-encrypted secrets in Postgres, not Secret Manager | Accepted |
| [0008](0008-pipelines-compile-to-langgraph.md) | Pipelines compile to LangGraph graphs | Accepted |
| [0009](0009-litellm-with-native-escape-hatches.md) | LiteLLM as the default provider with native implementations | Accepted |
| [0010](0010-agpl-with-permissive-sdk.md) | AGPL-3.0 core, Apache-2.0 SDK edges, DCO | Accepted |
| [0011](0011-taint-based-capability-gating.md) | Taint-based capability gating as the primary injection defence | Accepted |
| [0012](0012-no-code-execution-in-mvp.md) | No arbitrary code execution before v2 | Accepted |
| [0013](0013-authorize-chokepoint-with-rls-backstop.md) | One `authorize()` chokepoint with RLS as a backstop | Accepted |

## Template

```markdown
# ADR-NNNN: Title

**Status:** Proposed | Accepted | Superseded by ADR-NNNN
**Date:** YYYY-MM-DD
**Deciders:** names

## Context
The forces at play. What makes this decision necessary and non-obvious.

## Decision
What we are doing, stated so that someone can act on it.

## Consequences
What becomes easier, what becomes harder, and what we now have to live with.

## Alternatives considered
Each option, and the specific reason it was rejected.
```
