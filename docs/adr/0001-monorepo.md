# ADR-0001: Single repository for all components

**Status:** Accepted
**Date:** 2026-10-06

## Context

The system has a Next.js frontend, a FastAPI backend, a LangGraph runtime, a connector
collection, shared packages, and Terraform. The contracts between them are tight: `openapi.json`
is generated from the backend and consumed by the generated TypeScript client, and a typical
feature ("add the Slack connector") touches a connector directory, a migration, an endpoint, and
a frontend icon.

## Decision

One repository, with `pnpm` workspaces plus Turborepo for JavaScript and `uv` for Python. CI is
path-filtered so each part of the tree runs only the tests it needs.

## Consequences

**Easier:** atomic cross-cutting changes with one review and one revert; no API version dance
between repos; one clone and one `make dev` for a newcomer; a single `AGENTS.md` entry point.

**Harder:** the repository grows large and `git log` is noisy; CI requires real path-filter
discipline or everything runs on everything; `CODEOWNERS` has to do more work to route reviews.

**Live with:** path filters are now load-bearing. A missing filter means contributors wait on
tests unrelated to their change, which is the main way this decision would go wrong in practice.
The duration targets in the testing strategy exist to make that visible.

## Alternatives considered

**Separate `web` / `api` / `connectors` repositories.** Rejected: the coordination tax applies
to nearly every change, and the generated API client would need publishing and version-bumping
on every endpoint change. The isolation benefit is real but is obtainable from path filtering
without the coordination cost.

**Git submodules.** Rejected: universally disliked, and a recurring source of broken or
partially-cloned checkouts for newcomers — precisely the audience we cannot afford to lose.
