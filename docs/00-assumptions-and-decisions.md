# 00 — Assumptions, Locked Decisions, and Pushback

This document exists so that no one downstream has to guess. If a decision here is wrong,
change it *here* first, then propagate.

## 1. Assumptions

These are stated defaults. We proceed on them unless contradicted.

| # | Assumption | Why it matters |
| --- | --- | --- |
| A1 | Build capacity is one maintainer plus AI coding agents at first; outside contributors arrive after MVP. | Roadmap is sized in **agent-weeks** (one focused week of maintainer-directed AI implementation), not team sprints. Favours boring, well-documented patterns over clever ones. |
| A2 | Postgres is the single source of truth, including `pgvector` for memory and the LangGraph checkpointer. | No separate vector database, no separate state store, until measured pain. One backup story, one migration story. |
| A3 | BYO LLM keys only through v1. The platform never resells inference. | Removes the hardest abuse, fraud, and gross-margin problems from the critical path. Budgets still exist, but they protect *the user's* wallet. |
| A4 | Python 3.12, Node 22. `uv` for Python dependency management, `pnpm` workspaces plus Turborepo for JS. | Fast, lockfile-deterministic, works in CI and in `docker compose`. |
| A5 | Everything runs on Cloud Run. No GKE, no Kubernetes. | Scale-to-zero, per-service IAM, no cluster to operate. Revisit only if we need >60 min single requests or GPUs. |
| A6 | A hosted reference deployment exists, and `docker compose up` with the Firebase and GCS emulators is a first-class supported path. | Self-hosters are the OSS distribution channel and the escape hatch for platform-approval blockers (see §3). |
| A7 | English-only UI at MVP; i18n scaffolding (`next-intl`) is wired but only `en` is populated. | Avoids retrofitting string extraction later at near-zero upfront cost. |
| A8 | "Organization" and "workspace" are the same entity at MVP. Nested orgs arrive in v2 with SSO. | One tenancy column (`workspace_id`) everywhere; no premature hierarchy. |
| A9 | Single embedding model per deployment (`text-embedding-3-small`, 1536 dims) with the model recorded per row. | `pgvector` columns are fixed-dimension. Recording the model makes a future re-embed migration mechanical. |
| A10 | Soft delete (archive) is the default for user-visible resources; hard deletion happens only through the GDPR erasure job. | Matches the stated "delete means archive" requirement and keeps audit trails intact. |

## 2. Locked decisions

Confirmed with the project owner.

| Decision | Choice | Rationale |
| --- | --- | --- |
| Deployment posture | **Multi-tenant hosted SaaS first**, self-host supported secondary | Tenancy isolation and Postgres RLS are on the critical path from day one rather than being a retrofit. |
| License | **AGPL-3.0-only** for the core | Prevents a closed-source SaaS fork from reselling the platform without contributing back. Keeps a future dual/commercial license open since copyright stays with contributors under DCO. |
| License exception | `packages/api-client`, `packages/sdk`, `packages/connector-sdk` are **Apache-2.0** | Nobody should have to AGPL their own app to call our API or ship a connector. The ecosystem needs permissive edges. |
| Contribution agreement | **DCO** (`Signed-off-by`), not a CLA | A CLA measurably deters drive-by contributors. DCO is enforceable in CI with zero friction. |
| Doc delivery | Foundations first, then designs | This batch: index, 00, 01, 02, 04, 05. |

## 3. Pushback: requirements that are risky, contradictory, or over-scoped

This is the most important section in this document. Four of the stated requirements cannot
be built as written.

### 3.1 "Read their Instagram feed or messages" — not achievable for personal accounts

Meta **deprecated the Instagram Basic Display API on 4 December 2024**. The remaining paths
are the Instagram API with Instagram Login and the Instagram Graph API, both of which require
a **Business or Creator** account linked through a Meta app that has passed **App Review**.
Personal-account feed reading has no API at all. Direct-message access requires
`instagram_business_manage_messages`, which is review-gated and limited to business accounts
with messaging enabled. Content publishing is capped (25 API-published posts per rolling
24 hours) and does not cover every media type.

**Proposed alternative:** scope the Instagram connector to *business/creator accounts only*,
support publish plus comment and mention management plus insights, and state the personal-account
limitation in the connector manifest and the UI before the user connects. Ship it in **v2**,
behind App Review. Do not promise feed reading.

### 3.2 "Read their LinkedIn feed or messages" — no API exists

LinkedIn offers `w_member_social` for posting as a member through the self-serve "Share on
LinkedIn" product, and that is genuinely available. There is **no public API for reading a
member's feed, and none for reading or sending messages**. The Marketing Developer Platform
is partner-gated, application-reviewed, and oriented at organization pages and ads — not
personal feeds. Any product that reads a LinkedIn feed is doing browser automation, which
violates LinkedIn's User Agreement and gets accounts banned.

**Proposed alternative:** LinkedIn connector supports **publish and schedule posts as the
member, plus organization-page posting and analytics** where the user is an admin. Explicitly
document "read feed" and "read messages" as *not supported, by platform constraint*. Ship in
**v2**.

### 3.3 Gmail requires a paid, recurring third-party security assessment

Every useful Gmail scope — including `gmail.send` — is classified by Google as a
**restricted scope**. Using one in a published app with more than 100 users requires OAuth
app verification *plus* a **CASA (Cloud Application Security Assessment) Tier 2 or 3**
assessment performed by a Google-authorized lab assessor, repeated **annually**. Realistic
cost is low-thousands of USD per year for a small app, and elapsed time is commonly 6-12
weeks, much of it waiting. This is a hard dependency on an external party, it cannot be
compressed by working harder, and it must start early.

**Proposed mitigation — a three-track strategy:**

1. **Self-host / BYO OAuth client (available day one, no verification).** The user creates
   their own Google Cloud OAuth client in their own project and pastes the client ID and
   secret into their workspace. Their app stays in testing mode, they are their own test
   user, and Google requires no verification. Every connector supports this mode.
2. **Hosted app in testing mode (≤100 users).** Covers the entire private-beta period while
   verification and CASA run in parallel. Start the verification submission in **Phase 0**,
   not when we need it.
3. **SMTP/App-Password fallback for sending only.** Google still supports app passwords for
   SMTP on accounts with 2FA. A `smtp` connector gives "send an email as me" with zero OAuth
   verification burden, which covers the headline MVP flow. A separate `email-platform`
   connector (Resend or SendGrid) sends from a platform domain for users who do not care
   about the `From` address.

MVP therefore ships the headline "send an email with an attachment" flow via tracks 1 and 3,
and Gmail *reading* lands when verification clears.

### 3.4 "Multiple accounts per user device, each with its own connections, memory, and keys" conflates two things

Firebase Authentication maintains **one active user per `Auth` instance**, persisted under a
single storage key. There is no supported multi-session model. People hack around it with
multiple named `initializeApp` instances, but that gives you N independent token lifecycles
in the browser, no server-side revocation, and no device list. Separately, Firebase ID tokens
are valid for one hour and **revocation is not immediate** unless every request pays for a
`checkRevoked` lookup against Firebase. Firebase also has no notion of organizations;
Identity Platform "tenants" isolate entire user pools, which is the wrong shape.

What the requirement actually describes is two features wearing one coat:

- *"Sign in with Google or GitHub or email and land on the same account"* → **linked identity
  providers on one Firebase user**.
- *"Separate sets of connections, memory, and keys that I can switch between"* → **workspaces**,
  not identities.

**Proposed design:** Firebase is the identity provider only. On login we exchange the Firebase
ID token for **our own `__Host-session` httpOnly cookie** backed by a `sessions` row. The
cookie holds a *session set*, so several real identities can be signed in simultaneously on one
device, with an `X-Account-Id` header selecting the active one. This gives true multi-account,
instant server-side revocation, and a device list — none of which Firebase alone provides.
The account switcher in the UI switches **workspace** for most users and **identity** for the
minority who need work-versus-personal separation. Full design in
[03-designs/auth-and-multi-account.md](03-designs/auth-and-multi-account.md).

### 3.5 Smaller flags

| Requirement | Concern | Proposal |
| --- | --- | --- |
| "Any other platform" connectors | Unbounded. A connector is ~1-2 agent-weeks including OAuth, approval policy, tests, and docs. | Ship 6 first-party connectors plus **generic HTTP and webhook plus MCP-consumer** connectors. The generic three cover "any other platform" for power users; the connector SDK and recipe make community contributions the scaling mechanism. |
| "Sandboxed code execution" in MVP | Arbitrary code execution is the single largest attack surface in the product. | MVP has **no arbitrary code execution**. Data transforms use a fixed, declarative, pandas-backed node library. Real sandboxing (Cloud Run job per execution, no egress, read-only FS, hard CPU/mem/wall caps) lands in v2 with its own threat model review. |
| Visual pipeline editor in MVP | A node-graph editor is a multi-week frontend project on its own. | MVP has **no pipeline editor**. Scheduled work is expressed as a saved agent plus a schedule, which covers "send me the discrepancies every Monday at 9am". The React Flow editor lands in v1. |
| Both Cloud Tasks *and* Pub/Sub | Picking "and/or" without deciding leads to two overlapping dispatch paths. | **Decided:** Cloud Tasks for *work dispatch* (named tasks give idempotency, per-queue concurrency caps, scheduled delivery, retry policy). Pub/Sub for the *domain event bus* (fan-out to notifications, usage rollups, GCS object notifications). Both, with non-overlapping jobs. See [ADR-0004](adr/). |
| One Cloud Scheduler job per user schedule | Cloud Scheduler is a managed GCP resource per job. Thousands of user schedules means quota pressure, IAM churn, and schedules that live outside the database. | **Decided:** exactly **one** Cloud Scheduler job, firing every minute into a dispatcher endpoint that queries the `schedules` table for due runs and enqueues Cloud Tasks. Timezone-correct via `croniter` plus `zoneinfo`. User schedules stay ordinary rows. |
| "Never over-test" alongside a very large surface | These pull in opposite directions and the default failure mode is a slow, flaky suite nobody trusts. | Testing doc defines an explicit **do-not-test list** and ties each suite to a path filter, so a connector PR never waits on frontend E2E. |

## 4. Open questions

Prioritized. None block starting Phase 0.

| # | Question | Default if unanswered |
| --- | --- | --- |
| Q1 | Who pays for, and signs, the Google CASA assessment and the Meta/LinkedIn app reviews? This needs a legal entity and a budget. | Hosted app stays in testing mode (≤100 users); self-host with BYO OAuth client is the only production path. |
| Q2 | Is there a target launch date or funding runway that should compress the roadmap? | Sequence as written; MVP at roughly 10 agent-weeks. |
| Q3 | Product name and domain — is "Younique" final? It affects the package namespace, OAuth app names, and the MCP server identifier, all of which are painful to rename after OAuth verification. | Proceed with `younique` as the package and service prefix. |
| Q4 | Do we need SOC 2 within 12 months? It changes audit-log retention, access review, and vendor requirements. | Build SOC-2-compatible controls (audit log, least privilege, change management) but do not pursue certification. |
| Q5 | Data residency commitments? EU-only storage for EU users is a multi-region schema concern, not a later toggle. | Single region `us-central1`, with `europe-west1` as a documented v2 deployment target. |
| Q6 | Is Langfuse acceptable as the LLM-observability sink, or is LangSmith preferred? | **Langfuse** — OSS and self-hostable, which matters for an AGPL project; Cloud Trace handles infrastructure tracing. |
| Q7 | Should workspaces support guest users who are not members at MVP (needed for "share with specific people" to an email that has no account)? | Yes — invitation-by-email creates a pending grant that resolves on signup. |
| Q8 | Maximum artifact size? This sets GCS lifecycle, scan timeouts, and Cloud Run memory. | 100 MB per file at MVP, 1 GB per workspace on the free tier. |
| Q9 | Do we ship a public connector marketplace, or is contribution via pull request sufficient? | Pull request only through v1. A marketplace implies code review at runtime and a trust model we are not ready for. |
| Q10 | Who is the security contact in `SECURITY.md`, and is there a disclosure mailbox? | Maintainer email plus GitHub private vulnerability reporting enabled. |

## 5. Additional libraries, with justification

| Library | Role | Why it, and what we rejected |
| --- | --- | --- |
| **LiteLLM** (Python SDK, not the proxy) | Normalizes 100+ providers' chat, streaming, tool-calling, and reasoning parameters | Fastest path to "any model, including new releases, without a redeploy". Rejected: LangChain chat models (couples us to LangChain's abstraction churn), OpenRouter (routes BYO keys through a third party, which contradicts the privacy promise), hand-rolled adapters (unbounded maintenance). **Mitigation for leaky abstraction:** a thin internal `LLMProvider` interface with LiteLLM as the default implementation and native Anthropic/OpenAI adapters where fidelity matters (extended thinking, Responses API). |
| **pgvector** with HNSW | Semantic memory retrieval | Already in Postgres, available on Cloud SQL, transactional with the rest of the schema. Rejected: Pinecone/Qdrant/Vertex Vector Search (a second datastore, a second consistency problem, and a second bill for a corpus that will be small per tenant). |
| **langgraph-checkpoint-postgres** | Durable agent state, interrupts, resume | First-party, and it is what makes approval gates and multi-hour runs survive a Cloud Run instance dying. |
| **SQLAlchemy 2.0 async + Alembic** | ORM and migrations | Mature async support, and Alembic is the only credible Python migration tool for a schema this size. Rejected: raw asyncpg (hand-written migrations at this scale is a mistake), SQLModel (thin wrapper, lags SQLAlchemy). |
| **asyncpg** | Postgres driver | Fastest async driver; required for `LISTEN/NOTIFY` fan-out used by live run streaming. |
| **structlog** | Structured JSON logging with a redaction processor | Redaction has to be a pipeline stage, not a convention. Integrates with Cloud Logging's JSON payload format. |
| **OpenTelemetry** plus **OpenLLMetry** (Traceloop) | Tracing across frontend, FastAPI, SQLAlchemy, httpx, and LLM calls | Vendor-neutral, so self-hosters point OTLP at Phoenix or Langfuse while hosted exports to Cloud Trace plus Langfuse. |
| **Langfuse** | LLM-specific traces, prompt versions, eval runs | OSS and self-hostable, which fits an AGPL project. Rejected: LangSmith (closed, and self-hosters cannot run it). |
| **Pydantic v2** | Request/response models, connector manifests, tool schemas, settings | One schema source that produces OpenAPI *and* JSON Schema for tool definitions. |
| **shadcn/ui** plus Tailwind CSS v4 plus Radix primitives | Component library | Source-in-repo rather than a dependency, so it can be restyled freely; Radix gives real keyboard and screen-reader behaviour, which the accessibility requirement needs. Rejected: MUI (heavy, hard to restyle), Chakra (weaker a11y primitives). |
| **TanStack Query** plus Zustand | Server-state cache and small client-state stores | Chat streaming needs imperative control that a pure-RSC model fights. Rejected: Redux Toolkit (ceremony), SWR (weaker mutation and cache-invalidation ergonomics). |
| **React Flow (xyflow)** | Pipeline editor and run visualization | The only mature React node-graph library; handles pan/zoom/minimap/edge routing. v1, not MVP. |
| **Shiki** | Code syntax highlighting | Compile-time TextMate grammars give VS Code-identical output with no client-side highlighter cost. Rejected: Prism (weaker grammars), Monaco (an entire editor for read-only display). |
| **FastMCP** (official Python MCP SDK) | MCP server and client | First-party; implements Streamable HTTP and the OAuth 2.1 resource-server requirements of the MCP spec. |
| **Playwright** | E2E | Cross-browser, strong tracing on failure, good CI story. |
| **pytest** plus `pytest-asyncio` plus `testcontainers` | Backend tests against a real Postgres | RLS and partial-index behaviour cannot be tested against SQLite. |
| **croniter** plus `zoneinfo` | Timezone-aware schedule evaluation | Handles DST transitions correctly, which naive cron math does not. |
| **python-magic** plus **ClamAV** | Artifact type detection and malware scanning | Magic bytes over trusting `Content-Type`; ClamAV runs as our own Cloud Run service so no file content leaves our perimeter. |
| **Terraform** plus **Terragrunt-style per-env dirs** | IaC | Mandated. Per-environment directories over workspaces, because workspace state collisions are a common and expensive mistake. |
