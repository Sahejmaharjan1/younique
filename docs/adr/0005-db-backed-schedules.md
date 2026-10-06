# ADR-0005: One Cloud Scheduler job driving database-backed schedules

**Status:** Accepted
**Date:** 2026-10-06

## Context

Users create their own cron schedules for agents and pipelines, in their own timezones. The
obvious GCP-native approach is one Cloud Scheduler job per user schedule.

## Decision

Exactly **one** Cloud Scheduler job, firing `* * * * *` into `POST /internal/scheduler/tick`.
The handler queries `app.schedules` for rows where `next_fire_at <= now()` using
`FOR UPDATE SKIP LOCKED`, creates a `runs` row with
`idempotency_key = "sched:{schedule_id}:{fire_at}"`, enqueues a Cloud Task named
`run-{run_id}`, and advances `next_fire_at` via `croniter` with `zoneinfo`.

User schedules are ordinary database rows. Two additional nightly Cloud Scheduler jobs exist for
rollups and retention.

## Consequences

**Easier:** schedules are transactional with the pipeline they belong to; pause, resume, and
edit are row updates; no GCP quota or IAM churn as users scale; a self-hoster needs no Cloud
Scheduler at all (any minute cron works); the next-fire preview is a pure function.

**Harder:** we own correctness. Three independent barriers protect against duplicate dispatch —
`SKIP LOCKED`, the unique `idempotency_key` containing the UTC fire instant, and the named Cloud
Task — because a duplicate email to the operator persona destroys trust immediately.

**Live with:** a one-minute floor on schedule granularity, which is acceptable; and the
dispatcher query must stay sub-millisecond, which the partial index
`ix_schedules_due ... WHERE state = 'active'` provides.

Timezone behaviour is defined rather than emergent: a spring-forward gap fires at the next valid
instant, a fall-back duplicate fires **once** (enforced by the UTC instant in the idempotency
key), and `next_fire_at` is computed from the previous *scheduled* time so drift cannot
accumulate.

## Alternatives considered

**One Cloud Scheduler job per user schedule.** Rejected: schedules become GCP resources rather
than application data, which means quota pressure, IAM and Terraform churn on every user action,
and a state that can diverge from the database. Pausing a schedule would be an API call to
another system that can fail independently.

**A persistent scheduler process** (APScheduler, Celery Beat). Rejected: it needs an
always-on singleton, which contradicts scale-to-zero and introduces a leader-election problem.

**Cloud Workflows.** Rejected: not designed for thousands of tenant-defined cron expressions,
and it would be a third execution engine.
