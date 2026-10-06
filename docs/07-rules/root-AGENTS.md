# AGENTS.md

Rules for anyone — human or AI — writing code in this repository. Read this fully before your
first change. Nested `AGENTS.md` files in `apps/web/`, `backend/`, `connectors/`, and `infra/`
add area-specific rules; they never contradict this file.

## What Younique is

An AI-native workspace. Users connect third-party services (Gmail, GitHub, Slack, Sheets),
ask for work in natural language, and build background agents and scheduled pipelines. They
bring their own LLM API keys and can use any model.

The product holds **other people's credentials and acts on their behalf.** Every decision in
this codebase should be read in that light.

## Stack

| Layer | Technology |
| --- | --- |
| Frontend | Next.js App Router, TypeScript, Tailwind v4, shadcn/ui, TanStack Query |
| Backend | FastAPI, Python 3.12, async throughout, SQLAlchemy 2.0, Pydantic v2 |
| Agents | LangGraph with the Postgres checkpointer |
| Data | Cloud SQL Postgres 16, `pgvector`, GCS |
| Auth | Firebase Authentication for identity; **our own session cookies** after that |
| Cloud | GCP: Cloud Run, Cloud Tasks, Pub/Sub, Cloud Scheduler, KMS, Secret Manager |
| LLM | `LLMProvider` interface; LiteLLM default plus native Anthropic/OpenAI |

## The ten rules

These are not style preferences. Violating one is a blocking review comment.

1. **Authorization goes through `authorize(principal, action, resource)`.** It is a FastAPI
   dependency. Never write a permission check in a route handler or a service function. CI
   fails on a route without either `authorize()` or an explicit `@public` marker.
2. **Secrets never reach the frontend.** Provider API keys and OAuth tokens are write-only from
   the client's perspective. Reads return `last4` and status. There is no endpoint that returns
   a key, for anyone, ever.
3. **Untrusted content is data, never instruction.** Anything from a connector, a file, a web
   fetch, or an external MCP server is `untrusted`. The trust level is a one-way ratchet. Never
   interpolate untrusted text into a system prompt. See
   `docs/03-designs/safety-and-prompt-injection.md`.
4. **Tenant scoping is not optional.** Every tenant table has `workspace_id`. The DB session
   dependency issues `SET LOCAL app.workspace_id`. Never use `SET` (it leaks across pooled
   connections); never bypass the session dependency.
5. **Soft delete, always.** `DELETE` endpoints set `archived_at`. Hard deletion happens only in
   the GDPR erasure job. The one exception: revoking a connection also calls the provider's
   revoke endpoint and zeroes the stored token ciphertext.
6. **Async all the way down.** No `requests`, no sync SQLAlchemy, no blocking I/O in a handler.
   A blocking call stalls the event loop, and with Cloud Run concurrency that is an outage.
7. **Money is `int` micro-USD.** Never a `float`. A custom lint rule enforces this.
8. **Errors are typed.** Raise a `ProblemDetail` subclass with a stable `code`. Bare
   `HTTPException` fails lint. Every user-resolvable error carries a `remediation`.
9. **Idempotency for anything that causes a side effect.** `Idempotency-Key` on POSTs; named
   Cloud Tasks; `ON CONFLICT DO NOTHING` on usage events. Cloud Tasks delivers at least once,
   so a handler's first action is a compare-and-swap claim.
10. **No comments that restate the code.** Comment only a constraint the code cannot express
    (a provider quirk, a security invariant, a non-obvious ordering requirement).

## Where things go

| Task | Location |
| --- | --- |
| New integration | `connectors/{key}/` — nothing else should need to change |
| New tool on an existing connector | `connectors/{key}/tools/` plus its `MANIFEST` |
| Newly released model | `packages/model-registry/models.yaml` — one YAML entry |
| New model provider (new API shape) | `backend/src/younique/llm/providers/` |
| New pipeline node | `backend/src/younique/pipelines/nodes/` — the editor renders from JSON Schema, so no frontend change |
| New API endpoint | `backend/src/younique/api/v1/{resource}.py` |
| Business logic | `backend/src/younique/services/` — never in a router |
| Graph changes | `backend/src/younique/agents/` |
| Permission changes | `backend/src/younique/authz/policy.py` **and** `backend/tests/authz/expectations.yaml` |
| UI screen | `apps/web/app/(app)/{route}/` plus `apps/web/features/{feature}/` |
| Infrastructure | `infra/terraform/` |
| A decision worth remembering | `docs/adr/NNNN-title.md` |

Full table with more cases: `docs/07-repo-and-contributor-workflow.md` §3.

## Commands

```bash
make dev            # full local stack: Postgres, Firebase emulator, fake GCS, Langfuse
make test           # everything
make test-authz     # the authorization matrix — run this if you touched permissions
make lint           # ruff + eslint + prettier
make types          # mypy --strict + tsc --noEmit
make migrate        # alembic upgrade head
make revision m="add x"   # autogenerate — ALWAYS read the generated SQL by hand
make openapi        # regenerate openapi.json (commit the result)
make seed           # populate dev data
```

## Before you open a PR

- Conventional Commit message, `Signed-off-by` present (DCO — we do not use a CLA).
- Tests for the behaviour you changed. See `backend/tests/AGENTS.md` for what we do and do not
  test — **do not add tests for things on the do-not-test list.**
- Touched an endpoint? Run `make openapi` and commit the result.
- Touched permissions? Update `tests/authz/expectations.yaml`.
- Added a connector tool? Set its risk class, write `summarize_for_approval` if it is
  `high` risk, and set `produces_untrusted_content` correctly on its permission bundle.
- Migration? Expand-and-contract only; read the generated SQL; `CREATE INDEX CONCURRENTLY` in
  its own non-transactional migration.

## Things that will waste your time if you do not know them

- **Alembic must never touch the `langgraph` schema.** Those tables belong to
  `langgraph-checkpoint-postgres` and are created by its own `setup()`. An autogenerated
  migration against them corrupts live suspended agent runs. CI checks this.
- **Cloud SQL has a fixed extension allowlist.** `pg_uuidv7` is not available, so UUIDv7 keys
  are generated in Python with `uuid6.uuid7()`.
- **PgBouncer runs in transaction mode** for the worker fleet, so session-scoped features
  (`LISTEN/NOTIFY`, `SET` outside a transaction, prepared statements) must bypass it.
- **Return HTTP 200 from a task handler on a *business* failure.** Returning 5xx makes Cloud
  Tasks retry a job that will fail identically. Only infrastructure failures return 5xx.
- **Reasoning blocks from providers are opaque.** Redacted or encrypted thinking blocks must be
  stored and passed back byte-identical or the provider rejects the next turn.
- **`always_allow` does not survive tainting.** A high-risk tool in a run that has read
  untrusted content still requires approval. That is intentional and load-bearing.

## Planning documents

`docs/` is the authoritative design. Start with `docs/README.md`. If your change contradicts a
design document, change the document in the same PR or write an ADR — do not leave the code and
the plan disagreeing.
