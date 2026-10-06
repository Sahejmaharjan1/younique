# Younique — Planning Documents

Younique is an open-source, AI-native workspace: a chat interface where users connect
third-party services, ask for things in natural language, and build background agents and
scheduled pipelines — using their own LLM API keys and any model.

This directory is the authoritative plan. It is written to be committed as-is and to be the
first thing a new contributor (human or AI) reads.

## Reading order

New contributors should read, in order: [00](00-assumptions-and-decisions.md),
[01](01-product-scope-and-roadmap.md), [02](02-system-architecture.md), then whichever
design document covers their area.

## Document index

### Foundations

- [00-assumptions-and-decisions.md](00-assumptions-and-decisions.md) — Assumptions, locked
  decisions, open questions, and **requirements we are pushing back on**. Read this first.
- [01-product-scope-and-roadmap.md](01-product-scope-and-roadmap.md) — Personas, scope
  boundaries, and the Phase 0 / MVP / v1 / v2 / Later roadmap with exit criteria.
- [02-system-architecture.md](02-system-architecture.md) — Context and container diagrams,
  service boundaries, key request flows, GCP deployment topology.

### Technical designs

- [03-designs/auth-and-multi-account.md](03-designs/auth-and-multi-account.md) — Firebase
  Auth, our session layer, multi-account switching, device list, consent gating.
- [03-designs/authorization-and-sharing.md](03-designs/authorization-and-sharing.md) — RBAC
  plus resource ACLs, the single `authorize()` chokepoint, share links, RLS backstop.
- [03-designs/secrets-and-byok.md](03-designs/secrets-and-byok.md) — Envelope encryption
  with Cloud KMS, BYO provider keys, connector token storage, rotation, redaction.
- [03-designs/model-registry-and-routing.md](03-designs/model-registry-and-routing.md) —
  Provider-agnostic LLM abstraction, hot-reloadable model registry, reasoning support,
  provider error taxonomy and fallback.
- [03-designs/connector-framework.md](03-designs/connector-framework.md) — Connector
  manifest, OAuth, granular per-connection permissions, health, and the
  platform-approval strategy (Google CASA, Meta review, LinkedIn gating).
- [03-designs/agent-runtime.md](03-designs/agent-runtime.md) — LangGraph state schema, graph
  topology, Postgres checkpointing, approval interrupts, sub-agents, budgets.
- [03-designs/pipeline-engine.md](03-designs/pipeline-engine.md) — Node registry, DAG
  compilation to LangGraph, scheduling, run monitoring.
- [03-designs/memory-system.md](03-designs/memory-system.md) — Scopes, write policy,
  versioning and conflict resolution, hybrid retrieval, token budgeting.
- [03-designs/artifacts.md](03-designs/artifacts.md) — Direct-to-GCS uploads, type
  detection, malware scanning state machine, versioning, previews, signed downloads.
- [03-designs/usage-and-cost.md](03-designs/usage-and-cost.md) — Append-only usage ledger,
  price snapshotting, rollups, budgets and enforcement.
- [03-designs/mcp-server.md](03-designs/mcp-server.md) — Exposing tools/agents/pipelines over
  MCP with OAuth 2.1, and consuming external MCP servers as connectors.
- [03-designs/safety-and-prompt-injection.md](03-designs/safety-and-prompt-injection.md) —
  Provenance tainting, capability gating, egress control, sandboxed execution.

### Contracts and implementation

- [04-database-schema.md](04-database-schema.md) — Full Postgres schema, ER diagrams,
  indexes, partitioning, migration strategy.
- [05-api-design.md](05-api-design.md) — Resource list, conventions, SSE streaming, error
  format, idempotency, OpenAPI and client-generation plan.
- [06-frontend-architecture.md](06-frontend-architecture.md) — Route map, state and data
  fetching, component library, key screens, UX principles.
- [07-repo-and-contributor-workflow.md](07-repo-and-contributor-workflow.md) — Monorepo
  tree, "where do I put X?", coding standards, CI/CD, release process.
- [07-rules/](07-rules/) — Drafts of `AGENTS.md` and nested per-area rules files, plus the
  "how to add a connector / model provider / agent tool / pipeline node" recipes.

### Operations and assurance

- [08-security-and-privacy.md](08-security-and-privacy.md) — STRIDE threat model, controls
  matrix, privacy and compliance checklist, terms and consent flow.
- [09-observability.md](09-observability.md) — Logging, OpenTelemetry, LLM tracing with PII
  redaction, dashboards, SLOs, alerting.
- [10-testing-strategy.md](10-testing-strategy.md) — Critical E2E flows, focused backend
  tests, deterministic agent tests, connector contract tests, and what we will *not* test.
- [11-risk-register.md](11-risk-register.md) — Technical, platform-approval, cost, and
  security risks with owners and mitigations.
- [12-backlog.md](12-backlog.md) — Epics to stories with acceptance criteria, sizing,
  dependency order, and area tags.

### Decision records

- [adr/](adr/) — Architecture Decision Records. One file per decision, never edited after
  acceptance; superseded by a new ADR instead.

## Status

| Document | Status |
| --- | --- |
| 00 Assumptions and decisions | Drafted |
| 01 Product scope and roadmap | Drafted |
| 02 System architecture | Drafted |
| 03 Auth and multi-account | Drafted |
| 03 Authorization and sharing | Drafted |
| 03 Secrets and BYOK | Drafted |
| 03 Model registry and routing | Drafted |
| 03 Connector framework | Drafted |
| 03 Agent runtime | Drafted |
| 03 Pipeline engine | Drafted |
| 03 Memory system | Drafted |
| 03 Artifacts | Drafted |
| 03 Usage and cost | Drafted |
| 03 MCP server | Drafted |
| 03 Safety and prompt injection | Drafted |
| 04 Database schema | Drafted |
| 05 API design | Drafted |
| 06 Frontend architecture | Drafted |
| 07 Repo and contributor workflow | Drafted |
| 07 Rules file drafts | Drafted |
| 08 Security and privacy | Drafted |
| 09 Observability | Drafted |
| 10 Testing strategy | Drafted |
| 11 Risk register | Drafted |
| 12 Backlog | Drafted |
| ADRs 0001-0013 | Accepted |

The planning set is complete. Phase 0 begins at
[12-backlog.md](12-backlog.md) story `P0-A1`, with `P0-F6` (Google OAuth verification) starting
in parallel on day one because its elapsed time is external to the project.
