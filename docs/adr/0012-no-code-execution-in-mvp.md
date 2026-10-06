# ADR-0012: No arbitrary code execution before v2

**Status:** Accepted
**Date:** 2026-10-06

## Context

The requirements mention sandboxed code execution, and the retail persona's job — "clean this
feed and compare it with last week" — is the sort of task a developer would naturally solve by
having the model write pandas code and running it.

Arbitrary code execution is also the single largest attack surface the product could have. It
sits directly downstream of untrusted content (ADR-0011), so a prompt-injected agent writing and
executing code is the worst-case path in the entire threat model.

## Decision

**MVP and v1: no server-side code execution of any kind.** Data transformation uses a fixed,
declarative, pandas-backed node library (`transform.clean`, `transform.diff`,
`transform.aggregate`, and so on) with validated parameters. `ai.extract` with an output schema
covers much of what remains.

Model-generated code is displayed with syntax highlighting and can be previewed in a browser
iframe sandbox on a separate origin, on an explicit click. It is never executed server-side.

**v2**, with its own threat-model review before merge: one Cloud Run Job execution per code run,
**zero network egress**, no credentials of any kind, read-only filesystem except a `tmpfs`
`/tmp`, 2 vCPU / 2 GB / 60 s hard caps, a pinned package allowlist with no runtime `pip install`,
and all I/O through pre-signed GCS URLs baked into the job. Classified `risk = high`, defaulting
to `ask_each_time`, with the full code shown in the approval dialog.

## Consequences

**Easier:** the largest attack surface simply does not exist for the first two phases. MVP ships
materially sooner. The declarative nodes are also more debuggable for non-technical users, who
can read and edit a form but not a Python snippet.

**Harder:** some transformations are awkward or impossible declaratively, and developers will
ask for this. The honest answer is "v2, and here is the design" rather than a weaker interim
version.

**Live with:** the node library must be broad enough to be useful. If a gap appears repeatedly,
the right response is a new node type (half a day, and no new attack surface) rather than
accelerating the sandbox.

## Alternatives considered

**`RestrictedPython`, `exec` with a guard, or an in-process AST allowlist.** Rejected firmly:
every such approach has been broken repeatedly, and a single escape is total compromise of a
process holding decrypted user credentials. This is the most tempting shortcut and the most
dangerous.

**A shared long-lived sandbox pool** for lower latency. Rejected: cross-tenant contamination
risk for a marginal gain, in a feature that is not latency-sensitive.

**Hosted sandboxes (E2B, Modal, Daytona).** Fast to ship and genuinely well-engineered.
Rejected: it sends user data and user-derived code to a third party, which contradicts the
privacy posture that justifies BYOK, and it adds a vendor to the trust boundary for a feature we
can build on Cloud Run Jobs with strictly fewer parties involved.

**WASM / Pyodide server-side.** Rejected: pandas and numpy support is incomplete and the
performance for real data work is poor. Pyodide *is* used client-side for artifact previews,
where the browser already provides the sandbox.
