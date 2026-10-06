# backend/AGENTS.md

Rules for `backend/`. The root `AGENTS.md` applies too. Area files:
`src/younique/agents/AGENTS.md` for the LangGraph runtime.

## Layering — never skip a layer

```
api/v1/{resource}.py   routers: validate, authorize, call ONE service fn, serialize
services/              business logic, transactions, orchestration
models/                SQLAlchemy ORM
core/db.py             the session dependency — the ONLY place tenant context is set
```

- A router longer than ~25 lines is doing something a service should do.
- A service never imports from `api/`.
- A model never contains business logic beyond trivial properties.
- `authz/` is imported by routers (as a dependency) and by services (for tool-time re-checks).

## Three entrypoints, one package

`main_api.py`, `main_worker.py`, `main_mcp.py`. They share models, `authorize()`, the connector
registry, and the LLM layer — which is why this is one package and not three. They are deployed
as separate Cloud Run services because their scaling and ingress needs are opposite.

`worker` and the `/internal/*` routes must never be reachable from the public internet. They
are not mapped in the ALB URL map, **and** they verify the OIDC token's audience. Both, always.

## Database

```python
# The ONLY correct way to get a session
async def get_db(p: Principal = Depends(get_principal)) -> AsyncSession:
    async with session_factory() as s, s.begin():
        await s.execute(text("SET LOCAL app.workspace_id = :w"), {"w": str(p.workspace_id)})
        await s.execute(text("SET LOCAL app.user_id = :u"), {"u": str(p.user_id)})
        yield s
```

- **`SET LOCAL`, never `SET`.** `SET LOCAL` resets on commit or rollback. A plain `SET` leaks
  one tenant's context onto the next request that borrows the pooled connection. This is the
  single most dangerous possible bug in this codebase.
- Never construct a session outside this dependency. Background jobs use
  `system_session(workspace_id=...)` which does the same thing explicitly.
- Always `select()` with explicit columns or `load_only()` on hot paths. Never a bare
  `select(Model)` in a list endpoint.
- No lazy loading. `lazy="raise"` is configured globally, so an unexpected N+1 raises instead of
  silently issuing 200 queries. Use `selectinload` or `joinedload` deliberately.
- Add an index only with a named query that needs it, stated in the PR.

## Migrations

```bash
make revision m="add artifact scan columns"
# then READ backend/migrations/versions/*.py BY HAND. Always.
```

- Expand-and-contract only. Rollback is a Cloud Run traffic shift, so the previous image must
  work against the new schema.
- `CREATE INDEX CONCURRENTLY` goes in its own migration file with
  `transactional_ddl = False` — Postgres refuses it inside a transaction.
- New constraints: `ADD CONSTRAINT ... NOT VALID` then a separate `VALIDATE CONSTRAINT`, so the
  write lock is brief.
- Every migration runs with `lock_timeout = 3s`. A migration that cannot get its lock must fail
  fast rather than queue behind a long read and stall every write in the database.
- Backfills over 10,000 rows go in `migrations/data/` as a batched, resumable script.
- **Never reference the `langgraph` schema.** CI enforces this.

## Errors

```python
class ProblemDetail(Exception):
    status: int
    code: str                     # stable, machine-readable, in the taxonomy
    title: str
    detail: str | None
    retryable: bool = False
    remediation: Remediation | None = None
```

- Every code must exist in `docs/05-api-design.md` §2. Adding one means updating that table.
- Provider and connector SDK exceptions are **normalized before they propagate**. Those
  exception strings routinely echo the `Authorization` header, and a raw one must never reach a
  log, a trace, an API response, or a user.
- Any error a user can fix carries a `remediation` with an `action` the frontend renders as a
  button.

## Logging and tracing

- `structlog` only. `print` fails lint. The redaction processor is the reason — bypassing it
  bypasses secret scrubbing.
- Bind context once: `log = logger.bind(run_id=..., workspace_id=...)`.
- Never log a request or response body wholesale. Log the fields you need.
- Prompt and completion content is **not** traced by default. A workspace opts in, and the
  secret patterns still apply. See `docs/09-observability.md`.

## Secrets

- All crypto goes through `crypto/envelope.py`. Never call KMS or `AESGCM` directly.
- AAD is always bound to `workspace_id || secret_kind || row_id || key_version`. Omitting it
  lets an attacker with write access swap another tenant's ciphertext into their row.
- Decrypt as late as possible and hold plaintext in the narrowest scope possible.
- `SecretStr` for anything sensitive in a Pydantic model, so an accidental `repr` is safe.

## Background tasks

```python
@router.post("/internal/tasks/agent-run")
async def agent_run(body: AgentRunTask, _=Depends(verify_oidc(audience=...))):
    claimed = await claim_run(body.run_id)     # CAS: queued -> running
    if not claimed:
        return Response(status_code=200)       # duplicate delivery, already handled
    ...
```

- Cloud Tasks delivers **at least once**. The first action is always a compare-and-swap claim.
- Return 200 on terminal business failures, 5xx only on infrastructure failures.
- An approval suspension returns 200 and releases the instance. Never hold a container waiting
  for a human.
- Enqueue with a deterministic task name for deduplication.
- Publish domain events through the **outbox**, never directly to Pub/Sub — "insert a row and
  publish" is not atomic, and a rollback after a successful publish emits an event for work
  that never happened.

## Testing

See `backend/tests/AGENTS.md`. The short version: `testcontainers` Postgres (never SQLite —
RLS and partial indexes do not exist there), no network in unit tests, `respx` in strict mode
so an unexpected HTTP call fails the test.
