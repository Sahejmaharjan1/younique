# ADR-0007: Envelope-encrypted secrets in Postgres, not Secret Manager

**Status:** Accepted
**Date:** 2026-10-06

## Context

Each user stores LLM provider API keys and OAuth tokens for connected services. These are
credentials to someone else's account with real billing and real data access attached, and there
may eventually be tens or hundreds of thousands of them, with OAuth tokens rotating hourly.

## Decision

Three-level envelope encryption:

1. A per-environment **KEK** in Cloud KMS, rotated every 90 days, which never leaves KMS.
2. A per-**workspace** DEK (random AES-256), wrapped by the KEK, stored in
   `app.encryption_keys.dek_wrapped`.
3. Secret ciphertext as `bytea` in Postgres, AES-256-GCM, with **additional authenticated data
   bound to `workspace_id || secret_kind || row_id || key_version`**.

Cloud Secret Manager is used for **platform** secrets only: OAuth client secrets, Firebase admin
credentials, the database password.

## Consequences

**Easier:** one transaction for "create the connection and store its token"; one backup story;
GDPR erasure becomes **crypto-shredding** (destroy the workspace DEK and every ciphertext for
that tenant is unrecoverable, including in PITR snapshots we cannot selectively edit); a KMS
unwrap is cached per request so the hot path pays no round trip.

**Harder:** we own the crypto implementation. All of it lives in `crypto/envelope.py` and
nothing else may call KMS or `AESGCM` directly.

**Live with:** plaintext exists in Cloud Run memory during use, which is an accepted boundary —
a compromised runtime can always read what it processes. Detection is via anomalous KMS unwrap
volume rather than prevention.

The AAD binding is the part most implementations omit and the reason this design is safe against
a specific attack: without it, an attacker with `UPDATE` access (SQL injection, a compromised
credential, a bad migration) can copy another workspace's ciphertext into their own row and the
application will decrypt and use it. With AAD bound to the row, that ciphertext fails
authentication and the decrypt raises loudly.

## Alternatives considered

**One Secret Manager secret per user key.** Rejected on five counts: it is priced and quota'd
for ops secrets rather than user data; six-figure secret counts are expensive and hard to garbage
collect; "create connection and store token" would span two systems non-atomically; its
soft-delete and version-retention semantics fight provable GDPR erasure; and two systems means
two independent backup timelines.

**Application-level encryption with a static key in an environment variable.** Rejected for
hosted use: no rotation, no per-tenant isolation, and the key is in the deployment config. It
*is* offered as the `env` KEK backend for local development and single-node self-host, with a
loud startup warning in production.

**Column-level encryption via `pgcrypto`.** Rejected: the key would have to be passed in SQL,
which puts it in query logs.
