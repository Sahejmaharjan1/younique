# ADR-0004: Cloud Tasks for work dispatch, Pub/Sub for the event bus

**Status:** Accepted
**Date:** 2026-10-06

## Context

The original requirement said "Cloud Tasks and/or Pub/Sub". Leaving that undecided would produce
two overlapping dispatch paths with different retry semantics, which is how a system ends up
with jobs that run twice in one code path and never in another.

The system has two genuinely distinct async needs: dispatching a specific unit of work to a
specific handler exactly once, and fanning a domain event out to several unrelated consumers.

## Decision

**Cloud Tasks for work dispatch.** Queues: `agent-runs`, `pipeline-runs`, `connector-sync`,
`memory-extract`. Chosen specifically for four properties: named tasks give free deduplication
(the basis of our at-most-once guarantee), per-queue `max_concurrent_dispatches` gives real
backpressure, scheduled delivery gives retry-at, and the retry policy is declarative rather than
hand-coded.

**Pub/Sub for the domain event bus.** Topics: `events`, `gcs-uploads`. Used where one event has
several consumers — `run.succeeded` feeding notifications, usage rollups, and user webhooks
simultaneously — which Cloud Tasks cannot express. Every subscription has a dead-letter topic
with an alert on its depth.

Events are published via a **transactional outbox**, never directly, because "insert a row and
publish" is not atomic and a rollback after a successful publish would emit an event for work
that never happened.

## Consequences

**Easier:** per-tenant and per-queue rate limiting; idempotency by task name; fan-out without
coupling producers to consumers; a clean rule for which to use.

**Harder:** two systems to operate and understand. Trace context must be propagated manually
through both, or background runs become orphan traces.

**Live with:** a handler's first action is always a compare-and-swap claim, because Cloud Tasks
delivers at least once. And a handler must return `200` on a terminal business failure — a `5xx`
makes Cloud Tasks retry a job that will fail identically.

## Alternatives considered

**Pub/Sub for everything.** Rejected: no per-message scheduling, no task-name deduplication, and
flow control is per-subscription rather than per-unit-of-work. Achieving at-most-once scheduled
dispatch on top of it means rebuilding what Cloud Tasks already provides.

**Cloud Tasks for everything.** Rejected: no fan-out. Every new consumer of `run.succeeded`
would require changing the producer.

**A Postgres-backed queue** (`SKIP LOCKED` polling). Rejected as the primary mechanism: it needs
its own worker-pool management and scaling, and it loses scale-to-zero. It *is* used for the
schedule dispatcher's due-row query, where the data already lives in Postgres (ADR-0005).
