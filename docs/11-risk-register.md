# 11 — Risk Register

Scored as **Likelihood** (L) × **Impact** (I), each 1-5. Risks above 12 need an active
mitigation in the current phase, not a plan for later. Ordered by score.

## 1. Platform and approval risks

These are the risks the project cannot solve by working harder, which makes them the most
dangerous category.

| ID | Risk | L | I | Score | Mitigation | Owner / phase |
| --- | --- | --- | --- | --- | --- | --- |
| **P1** | **Google OAuth verification plus CASA is slow, costly, and annually recurring.** All Gmail scopes are restricted; a published app over 100 users needs a Tier 2/3 assessment by an authorized assessor, typically 6-12 weeks elapsed and low-thousands USD per year. | 5 | 4 | **20** | Three-track strategy: self-host with BYO OAuth client (no verification), hosted app in testing mode for the ≤100-user beta, and an `smtp` connector that delivers the headline email flow with zero OAuth burden. **Submit in Phase 0** so the clock runs during MVP build. Prefer non-restricted scopes elsewhere (`drive.file` over `drive.readonly`). | Phase 0, story P0-F6 |
| **P2** | **Instagram and LinkedIn cannot do what the spec asks.** Meta deprecated the Instagram Basic Display API in Dec 2024, so personal-account feed reading has no API at all; LinkedIn has no public API for reading a member's feed or messages. | 5 | 3 | **15** | Re-scope both to publish-only (plus comments, mentions, and insights for Instagram business accounts) and state the limitation in the connector manifest, the connect dialog, and the generated docs page. Documented in [00 §3.1-3.2](00-assumptions-and-decisions.md). Do not promise reading. | Done in planning; v2 to build |
| **P3** | **Meta App Review rejects or stalls**, blocking the Instagram connector indefinitely. | 4 | 2 | 8 | v2 scope, so nothing in MVP or v1 depends on it. BYO Meta app lets individual users proceed. Marked "pending approval" in the UI rather than shipped-and-broken. | v2 |
| **P4** | **A provider changes terms to prohibit our use case** (agentic access, automated posting). | 2 | 4 | 8 | Connectors are isolated, so losing one is a feature removal rather than an outage. The generic HTTP, webhook, and MCP connectors mean power users are never fully blocked. Terms monitored per connector at each release. | Ongoing |
| **P5** | **Slack App Directory review delays public distribution.** | 3 | 2 | 6 | Ship as a private/manual install first, which requires no review. Directory listing is a growth task, not a functional dependency. | v1 |

## 2. Security risks

| ID | Risk | L | I | Score | Mitigation |
| --- | --- | --- | --- | --- | --- |
| **S1** | **Prompt injection causes an unauthorized action** — the defining risk of the product. | 4 | 5 | **20** | Architectural, not prompt-based: taint ratchet, capability gating where `always_allow` does not survive tainting, approval gates with provenance highlighting, egress allowlists, SSRF-safe HTTP with resolved-IP checks, Unicode tag stripping, step and tool-call limits capping blast radius, and the regression suite in [10 §4](10-testing-strategy.md). Residual risk published honestly in `SECURITY.md`. |
| **S2** | **Connector token or provider key compromise.** | 2 | 5 | 10 | Envelope encryption with AAD binding, KEK in KMS (a DB dump is useless), no endpoint returns key material to anyone, step-up re-auth on all secret operations, four-layer redaction, crypto-shredding for erasure, KMS decrypt audit logging with anomaly alerting. |
| **S3** | **Cross-tenant data leak.** | 2 | 5 | 10 | Two independent controls: the `authorize()` chokepoint (with a CI check that every route has it) and Postgres RLS with `FORCE ROW LEVEL SECURITY` and no `BYPASSRLS`. Exhaustive authorization test matrix. Cross-workspace returns `404`, not `403`. |
| **S4** | **Supply-chain compromise exfiltrates secrets** — the highest residual risk in the system, because a malicious dependency runs inside our trust boundary. | 2 | 5 | 10 | Hash-pinned lockfiles, Dependabot, `pip-audit`/`npm audit`, Trivy, CodeQL, Binary Authorization in v1, and VPC Service Controls egress restriction in v1. Honestly acknowledged as not fully mitigated. |
| **S5** | **Sandboxed code execution escape** (v2). | 2 | 5 | 10 | Deferred out of MVP entirely. When built: one Cloud Run Job per execution, zero network egress, no credentials, read-only FS, hard caps, I/O only via pre-signed URLs, and its own threat-model review before merge. |
| **S6** | **A malicious external MCP server attacks via tool descriptions ("rug pull").** | 3 | 3 | 9 | Schemas hashed at approval; any change disables the tool pending re-approval with a diff. All results untrusted, always. Namespaced so a server cannot shadow a first-party tool. |
| **S7** | **XSS via an artifact preview** (HTML, SVG). | 2 | 4 | 8 | DOMPurify, `Content-Disposition: attachment`, sandboxed iframe on a **separate origin** with a restrictive CSP, so an escape cannot reach session cookies. |
| **S8** | **A user sets `allow_when_tainted` broadly and is then exploited.** | 3 | 3 | 9 | Step-up re-auth plus a plain-language warning at the moment of the choice; a security review page listing every relaxed policy. Ultimately the user's decision, surfaced rather than hidden. |

## 3. Technical risks

| ID | Risk | L | I | Score | Mitigation |
| --- | --- | --- | --- | --- | --- |
| **T1** | **Database connection exhaustion** — `max_instances × pool_size` exceeds Cloud SQL `max_connections` and the whole app browns out. The classic serverless-plus-Postgres failure. | 4 | 4 | **16** | `max_instances` is a required Terraform argument with no default; documented connection math in [infra rules](07-rules/infra-AGENTS.md); `api` pool of 5; PgBouncer in transaction mode for the worker fleet; alerts on `db_pool_waiting`. |
| **T2** | **Scope creep delays any usable release.** The spec is roughly three products. | 4 | 4 | **16** | Phase gates with testable exit criteria; four items explicitly cut from MVP (pipeline editor, code execution, Slack/GitHub, sharing roles); the permanent out-of-scope list in [01 §5](01-product-scope-and-roadmap.md). Reviewed at each phase boundary. |
| **T3** | **LiteLLM lags frontier provider features** (extended thinking with interleaved tool use, the Responses API, caching controls). | 4 | 3 | 12 | Our own `LLMProvider` interface is the contract; native Anthropic and OpenAI implementations exist for fidelity; `model_providers.implementation` is a database value, so switching back to LiteLLM when it catches up needs no code change. |
| **T4** | **Duplicate or missed scheduled runs** — a duplicate email destroys the operator persona's trust immediately. | 3 | 4 | 12 | Three independent barriers: `FOR UPDATE SKIP LOCKED` on the due query, a unique `idempotency_key` on `runs` containing the UTC fire instant, and a named Cloud Task. Full DST test matrix. A 14-day zero-miss/zero-duplicate run is a v1 exit criterion. |
| **T5** | **LangGraph checkpoint format changes break suspended runs.** | 3 | 4 | 12 | Version pinned; schema isolated in its own namespace; CI asserts Alembic never touches it; the deploy checklist blocks an upgrade while any run is `awaiting_approval`. |
| **T6** | **Streaming reliability** — dropped tokens are the most noticeable possible bug. | 3 | 4 | 12 | Every event persisted to `run_events` with a monotonic `seq` before flush; resume endpoint with `last_event_id`; SSE disconnect, reconnect, and **resume-gap** metrics (a non-zero gap count is a bug the user notices before monitoring would). |
| **T7** | **`LISTEN/NOTIFY` fan-out does not scale** for live background-run tailing. | 3 | 2 | 6 | One shared listener per instance with in-process fan-out; abstracted behind `RunEventBus` so Memorystore Redis is a drop-in replacement with no call-site changes. |
| **T8** | **Agent reliability is poor in practice** — the agent fails at real tasks often enough that users give up. | 3 | 4 | 12 | Narrow, well-described tools with bounded inputs; full step visibility and "retry from here"; honest error messages with remediation; the nightly eval harness tracking tool-selection accuracy as a trend. Partly outside our control — it depends on model capability. |
| **T9** | **Memory feels creepy or wrong, and users disable it.** | 3 | 3 | 9 | Visible, editable, attributable, reversible by design; "inferred" badges with evidence links; `retrieved="3 of 47"` in the context block and in the UI; `preview-retrieval` as a "why did it remember this?" feature; per-set pause. |
| **T10** | **Migration causes downtime** — a lock-blocked migration stalls every write. | 2 | 4 | 8 | Expand-and-contract only; `lock_timeout = 3s` so a migration fails fast instead of queueing; `CONCURRENTLY` indexes in their own non-transactional migration; `NOT VALID` then `VALIDATE` for constraints; batched data migrations. |
| **T11** | **Artifact scanning becomes a bottleneck or fails open.** | 2 | 4 | 8 | Staging bucket means unscanned files are physically unservable; promotion *is* the clean signal; 60 s timeout **fails closed**; 100 MB cap; `scanner` scales independently; backlog alerting. |

## 4. Cost risks

| ID | Risk | L | I | Score | Mitigation |
| --- | --- | --- | --- | --- | --- |
| **C1** | **A runaway agent burns a user's provider credits.** | 3 | 4 | 12 | Per-run step, tool-call, wall-clock, and spend limits; three-point budget enforcement (preflight, per-call, post-hoc); pre-publish cost estimates on schedules; per-message cost shown where the decision is made; schedules **paused** on a budget block rather than left failing. |
| **C2** | **Our own GCP bill grows faster than usage** (Cloud Run min-instances, logging volume, Cloud Trace, egress). | 3 | 3 | 9 | Budget alerts at 50/80/100 %; `max_instances` everywhere; `min_instances = 0` except `api`; log exclusions for health checks and static assets; tail-based trace sampling; GCS lifecycle rules; observability budgeted at under 10 % of infra spend and reviewed monthly. |
| **C3** | **Platform-paid embeddings are abused** — the one place we pay for inference. | 3 | 2 | 6 | Workspace's own key preferred; 1 M tokens/month cap per workspace when using the platform key; metered into `usage_events` like any other call; a `local` embedding backend for self-hosters. |
| **C4** | **CASA assessment and app-review fees exceed budget** with no revenue. | 3 | 3 | 9 | Open question Q1 with a stated default: stay in testing mode and ship self-host as the production path. The product is functional without hosted Gmail. |

## 5. Project and community risks

| ID | Risk | L | I | Score | Mitigation |
| --- | --- | --- | --- | --- | --- |
| **J1** | **Single-maintainer bus factor.** | 4 | 4 | **16** | This entire planning set is the primary mitigation — the architecture, conventions, and rationale are written down rather than held in one head. Plus `AGENTS.md` files for AI-assisted continuity, ADRs capturing *why*, and a connector framework that makes the highest-volume contribution type self-contained. |
| **J2** | **Contributors cannot get started** — broken or slow local setup. | 3 | 4 | 12 | `docker compose` with full emulators (no cloud account needed); `make setup && make dev`; `make seed` for populated data; the **15-minute target enforced as a weekly CI job** on a clean runner, because setup docs rot silently. |
| **J3** | **AGPL deters adoption or contribution.** | 3 | 3 | 9 | Apache-2.0 on the SDK, API client, and connector SDK, so nobody has to AGPL their own app or connector. DCO rather than a CLA, since CLAs measurably deter drive-by contributors. Rationale documented so the choice is arguable rather than mysterious. |
| **J4** | **Slow CI drives contributors away.** | 3 | 3 | 9 | Path-filtered pipelines with per-job duration targets; a connector-only PR green in under 4 minutes; same-day flake quarantine rather than `--retries`. |
| **J5** | **Documentation drifts from the code.** | 4 | 2 | 8 | Connector docs pages **generated from manifests**; API reference generated from `openapi.json` with a committed-file drift check; the rule that a PR contradicting a design doc must update it or write an ADR in the same PR. |
| **J6** | **A security incident in a young OSS project damages trust permanently.** | 2 | 5 | 10 | `SECURITY.md` with private reporting and a 90-day coordinated-disclosure policy; honest published residual-risk list; security review triggers on sensitive paths; a pre-release security-review pass on each release diff; a breach runbook with an owner. |

## 6. Top risks and where they are handled

| Score | Risk | Primary mitigation lives in |
| --- | --- | --- |
| 20 | P1 Google CASA timeline and cost | [00 §3.3](00-assumptions-and-decisions.md), story P0-F6 |
| 20 | S1 Prompt injection | [safety-and-prompt-injection.md](03-designs/safety-and-prompt-injection.md) |
| 16 | T1 DB connection exhaustion | [infra-AGENTS.md](07-rules/infra-AGENTS.md), [02 §6](02-system-architecture.md) |
| 16 | T2 Scope creep | [01 §4-5](01-product-scope-and-roadmap.md) phase gates |
| 16 | J1 Bus factor | This entire `docs/` set |
| 15 | P2 Instagram and LinkedIn infeasibility | [00 §3.1-3.2](00-assumptions-and-decisions.md) |

## 7. Review cadence

Reviewed at every phase boundary and whenever a score changes by 4 or more. Each review records
what changed and why, in `docs/risk-reviews/YYYY-MM-DD.md`, so the register has a history rather
than just a current state. A risk that is fully mitigated moves to a closed section with the
evidence — not deleted, because the reasoning is useful when a similar risk appears.
