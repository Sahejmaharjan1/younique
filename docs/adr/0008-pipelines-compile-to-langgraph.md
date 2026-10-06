# ADR-0008: Pipelines compile to LangGraph graphs

**Status:** Accepted
**Date:** 2026-10-06

## Context

The product has three things that execute: chat turns, background agents, and user-defined
node-based pipelines. Pipelines look like a different problem — a declarative DAG rather than a
model-driven loop — which invites building a separate pipeline executor.

But a pipeline needs retries, cancellation, pause and resume, per-step input and output capture,
cost accounting, approval gates on destination steps, durable checkpointing so a two-hour run
survives an instance restart, and a run history UI. The agent runtime already has every one of
those.

## Decision

`pipeline_versions.graph` is a declarative JSONB DAG. A compiler builds a LangGraph `StateGraph`
from it at run time. Pipeline runs are `runs` rows with `kind = 'pipeline'`; node executions are
`run_steps` rows with `node_name` set.

There is no pipeline engine. There is one execution engine with two front ends.

## Consequences

**Easier:** one implementation of retry, cancel, pause, resume, checkpoint, budget, approval,
and cost attribution. The run-detail UI is literally the same component for an agent run and a
pipeline run. A pipeline step can invoke a full agent (`ai.agent` node) with no special plumbing,
because they are the same substrate.

**Harder:** the compiler must translate conditional edges, bounded fan-out (`control.foreach`),
and error handlers into LangGraph constructs. The DAG document becomes a versioned public
contract (`schema_version`), so changes to it need migration care.

**Live with:** `AgentState` carries fields only some runs use. That is the cost of the
discriminator-plus-nullable-fields shape, and it is far cheaper than three parallel state
schemas.

A running pipeline always executes a **published** immutable version, so editing never mutates
something mid-flight.

## Alternatives considered

**A separate declarative pipeline executor.** Rejected: it duplicates eight cross-cutting
concerns, and the duplicates will diverge. The specific failure I expect is two cost-attribution
paths that disagree, which destroys trust in the usage dashboard.

**Prefect, Dagster, or Airflow.** Rejected: all are operationally heavy for user-defined
per-tenant DAGs, none integrate with LangGraph checkpoints or our approval interrupts, and each
would be a second scheduler and a second run-history store. Airflow in particular is built for
operator-defined pipelines, not thousands of tenant-defined ones.

**Temporal.** Genuinely strong at durable execution, and the closest real alternative. Rejected:
it would replace LangGraph's checkpointer rather than complement it, requires operating a
cluster (contradicting ADR's Cloud-Run-only posture), and adds a large concept surface for
contributors.
