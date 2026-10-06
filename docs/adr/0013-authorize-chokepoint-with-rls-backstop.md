# ADR-0013: One `authorize()` chokepoint, with Postgres RLS as a backstop

**Status:** Accepted
**Date:** 2026-10-06

## Context

The system is multi-tenant, with workspace roles, resource-level ACLs, public share links,
scoped MCP tokens, personal access tokens, and agents acting on a user's behalf. There will be
well over a hundred endpoints.

Authorization bugs in systems like this are almost never "the policy was wrong". They are
"eleven places checked and the twelfth forgot". That is a coverage problem disguised as a
correctness problem.

## Decision

Two independent layers, each doing a job the other cannot.

**Primary: one function.** `authorize(principal, action, resource)` is invoked as a FastAPI
dependency before every route handler. Route handlers and service functions contain **zero**
permission logic. A CI check fails any route that has neither an `authorize()` dependency nor an
explicit `@public` marker. The expectation table lives in
`backend/tests/authz/expectations.yaml` as reviewed data, so changing a permission shows up in
the diff rather than inside a policy function.

**Backstop: Postgres RLS.** Every tenant table has `ENABLE` plus `FORCE ROW LEVEL SECURITY`
with a `workspace_id = current_setting('app.workspace_id')` policy. The application connects as
a non-owner role with no `BYPASSRLS`. The session dependency issues `SET LOCAL app.workspace_id`
inside the transaction.

## Consequences

**Easier:** exhaustive testing of a single function is tractable, so the authorization suite can
genuinely be complete; a forgotten check degrades to "returns no rows" rather than "returns
another tenant's rows"; and a reviewer has one file to read to understand the policy.

**Harder:** `authorize()` runs on nearly every request, so it must be one indexed query (it is,
and it is cached on `request.state`). List endpoints cannot check N resources individually, so
the readability predicate is composed into the list query's `WHERE` clause — otherwise pagination
counts would be wrong and there would be an N+1.

**Live with:**

- `SET LOCAL` rather than `SET`, absolutely. A plain `SET` leaks one tenant's context onto the
  next request that borrows the pooled connection. This is the single most dangerous possible bug
  in the codebase, and it has its own test.
- **Neither layer makes the other optional.** RLS cannot express role semantics (a `viewer`
  editing) and cannot catch cross-user access *within* a workspace (reading a colleague's
  connection), because it is tenant-scoped rather than user-scoped. `authorize()` cannot catch a
  hand-written query missing a `WHERE` clause. The failure modes are disjoint.
- No permission cache with a TTL. A revoked share that keeps working for 60 seconds is a real
  incident, and the queries are cheap enough that caching buys microseconds for a correctness
  hazard.

## Alternatives considered

**Checks inside each handler.** Rejected: this is the failure mode being designed against.

**An external policy engine (OPA, Cedar, OpenFGA).** Genuinely good tools. Rejected for now: a
network hop or an embedded engine on the hot path, a second policy language for contributors to
learn, and a sync problem between the engine's relationship data and Postgres. Revisit if the
policy grows beyond what one readable function can express — OpenFGA in particular would be the
right answer if we ever add hierarchical folder inheritance.

**RLS alone.** Rejected: it cannot express roles, resource ACLs, share links, or within-tenant
user isolation. It is a tenancy guarantee, not an authorization system.

**Role inheritance through a resource hierarchy** (folders granting permissions to contents).
Rejected: it is the feature that makes authorization systems impossible to reason about.
"Share the chat" plus "share the workspace" covers the real use cases, and projects exist as a
memory scope and an organizing label rather than a permission boundary.
