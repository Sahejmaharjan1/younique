# tests/AGENTS.md

Rules for tests. Full strategy and rationale: `docs/10-testing-strategy.md`.

## The governing principle

**Test what protects real risk. Do not test for coverage.**

A slow, flaky suite is worse than a smaller one, because contributors start ignoring red builds
and then the tests that *do* matter stop being believed. We have no coverage target and we will
not add one.

## Before you write a test, check the do-not-test list

These are deliberate omissions. **Do not add tests in these categories** — a PR that does will
get a review comment pointing here.

| Not tested | Why |
| --- | --- |
| LLM output quality, prompt wording, "does the agent choose well" | Nondeterministic, slow, expensive. Belongs in the nightly eval harness as a tracked trend, not a pass/fail gate. |
| Live calls to real LLM providers or real third-party APIs | Tests the vendor, not us. A nightly smoke job covers wire-format drift. |
| Generated code (`packages/api-client`, OpenAPI types) | Tests the generator. A drift check covers what matters. |
| Framework behaviour (FastAPI routing, Next.js rendering, React Flow interaction, Radix a11y) | Already tested upstream. |
| Getters, setters, trivial Pydantic models, `__repr__` | No risk. |
| ClamAV detection efficacy | That is ClamAV's job. We test that the *gate* works. |
| Every file format's preview rendering | One representative per MIME group is enough. |
| Visual regression and UI snapshots | Churns on every design change, catches almost nothing real. |
| Terraform plan contents beyond `validate`, `tflint`, `checkov` | Asserting on plan output is brittle and duplicates the tools. |
| Exact agreement with a provider's invoice | We cannot see their billing system and we do not model their discounts. Documented as an estimate. |
| Exhaustive connector field mapping | One happy path plus the error paths per connector. |

## What we do test, in priority order

1. **Authorization, permissions, tenant isolation.** The only place exhaustive testing is
   justified, because a gap is a data breach. Parametrized across the full
   principal × resource × action cross-product, with expectations in
   `tests/authz/expectations.yaml`.
2. **Prompt-injection regressions.** `tests/agents/test_injection.py`. Never weaken one to make
   a feature pass.
3. **Secrets handling.** Round-trip, AAD tamper-detection, and a leakage test that pushes a
   known-secret corpus through logs, traces, errors, and prompts asserting zero escape.
4. **Idempotency and at-most-once.** Duplicate task delivery, duplicate scheduler ticks,
   duplicate usage events.
5. **Money arithmetic.** Cost computation, price snapshot immutability, rollup reconciliation.
6. **Critical E2E flows.** The short list in `docs/10-testing-strategy.md` §2 and nothing more.
7. **Graph behaviour with mocked LLMs.** Gating, limits, taint, resume, cancellation.
8. **Connector contracts.** Against cassettes.

## Backend rules

- **Real Postgres via `testcontainers`. Never SQLite.** RLS, partial indexes, `tsvector`,
  `pgvector`, and advisory locks do not exist there, and those are exactly what we need to
  verify.
- One container per session, with each test in a transaction that is rolled back. Fast and
  isolated.
- **`respx` in strict mode.** An unexpected outbound HTTP call fails the test. This is how
  "the grant check happens *before* the request" becomes verifiable.
- No `time.sleep`. Freeze time with `freezegun` or inject a clock.
- Factories (`factory_boy`) over fixtures for entities. Fixtures for infrastructure.
- Every test that touches the database goes through the session dependency, so tenant context
  is set — a test that bypasses it is testing something production never does.

## Authorization tests

`tests/authz/expectations.yaml` is **data, reviewed as a document**. Changing a permission means
changing that file, which makes the change visible in review rather than buried inside a policy
function.

Specific assertions that must never regress:

- Cross-workspace access returns `404`, not `403`. A `403` confirms the resource exists.
- A share-link principal is denied every `tool.*` and `*_secret` action.
- An agent's effective permissions are the **intersection** of its owner's and its allowlist.
- Direct SQL as `younique_app` with no tenant context returns zero rows from every tenant table.

## Agent tests

`FakeChatModel` with scripted responses. **No real model calls, in any test, ever.**

Assert on the requests the fake received, not just the final output — "the model was asked with
the right tools and the right context" is usually the behaviour under test.

## E2E (Playwright)

Only the flows in `docs/10-testing-strategy.md` §2. Each must be:

- **Independent.** No ordering dependency, own data, parallel-safe.
- **Deterministic.** Mock LLM and provider responses at the network boundary. An E2E test that
  calls a real model is a flake generator.
- **Semantic in its selectors.** `getByRole`, `getByLabel`, `data-testid` as a last resort.
  Never a CSS class or an XPath.
- **Assertive about failure.** `expect` with auto-retry, never a bare `waitForTimeout`.
- **Traced.** Trace on first retry, so a CI failure is debuggable without reproducing locally.

A flaky E2E test is **quarantined within one day** (skipped with a linked issue) rather than
retried. A suite people re-run until it passes provides no signal.

## Which suites run on which PRs

Path-filtered — see `docs/07-repo-and-contributor-workflow.md` §6. The one exception:
**`backend-authz` runs on every backend or connector PR regardless of path**, because adding a
connector tool changes the authorization surface. It is cheap, and it is the suite whose failure
matters most.
