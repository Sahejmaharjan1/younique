# Architecture

Younique is one repository and one execution engine. Chat turns, agents, and pipelines compile to LangGraph and write to `app.runs` and `app.run_steps`.

| Service | Role |
| --- | --- |
| `web` | Next.js App Router. Routes and presentation only. |
| `api` | FastAPI. Sessions, authorization, chat streaming, connectors. |
| `worker` | Internal tasks: outbox drain, upload ingest, approval resume. |

Identity is Firebase. After one token exchange the browser holds an opaque `__Host-session` cookie (or `session` when `COOKIE_SECURE=false` for local HTTP). Multiple accounts on one device share a `session_group_id`. `X-Account-Id` only selects a session already in that group.

Every tenant table has row-level security. The request path sets `app.workspace_id` with `set_config(..., true)`, which is transaction-local. The application role `younique_app` cannot bypass RLS.

Secrets use envelope encryption. A per-workspace data key is wrapped by a KEK (`env`, `file`, or Cloud KMS). Ciphertext is bound to workspace, row, and key version, so a swapped ciphertext does not decrypt.

`authorize()` is the only permission decision. Postgres RLS is the backstop. High-risk tools that run after untrusted content still require approval even when the policy is `always_allow`.

Cloud SQL is reached over a private IP. One Cloud Scheduler tick drives database schedules. Cloud Tasks and Pub/Sub each have a dead-letter path. Deploys shift traffic from 0% to 10% to 100%, and rollback is a traffic shift.
