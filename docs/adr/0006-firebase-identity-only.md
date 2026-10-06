# ADR-0006: Firebase for identity only, with our own session layer

**Status:** Accepted
**Date:** 2026-10-06

## Context

Firebase Authentication is mandated. The product also requires multiple accounts per device with
separate connections, keys, and memory; a device and session list; and immediate revocation.

Firebase cannot express those. It maintains **one active user per `Auth` instance** under a
single storage key, its ID tokens live for an hour with revocation taking effect only at
refresh (unless every request pays for a `checkRevoked` lookup), and it has no server-side
session registry and no concept of organizations.

## Decision

Firebase proves identity. Nothing else.

On login, the client exchanges a Firebase ID token once for our own `__Host-session` httpOnly
cookie, backed by an `app.sessions` row. The Firebase token is then discarded and never used
again. Sessions created in the same browser share a `session_group_id`, so several real
identities can be signed in simultaneously; `X-Account-Id` selects the active one, and the
server only accepts an account that already has an unrevoked session **in the same group**.

The requirement's two halves are separated: linked identity providers on one Firebase user
handle "sign in with Google or GitHub and land on the same account", and **workspaces** handle
"separate sets of connections, memory, and keys".

## Consequences

**Easier:** true multi-account on one device; instant server-side revocation with no cache; a
device list with IP and last-seen; step-up re-auth as a first-class concept; one Firebase
verification per login instead of per request; and a drop-in path to generic OIDC for
self-hosters, because Firebase is confined to a single function.

**Harder:** we own session lifecycle, rotation, and CSRF. Two concepts (identity switching vs
workspace switching) must be explained in the UI without confusing people.

**Live with:** Firebase's `one account per email address` setting must stay **on**. The
alternative permits account takeover via an unverified email at a provider that does not
verify — so the account-exists-with-different-credential case is handled explicitly with a
link flow, and a Terraform comment explains why nobody should flip the setting.

## Alternatives considered

**Multiple named Firebase `Auth` instances for multi-account.** Rejected: N independent token
lifecycles in the browser, no server-side revocation, no device list.

**Firebase session cookies.** Rejected: still single-session, and revocation is still Firebase's
to decide.

**Replacing Firebase entirely.** Out of scope — it is a mandated component, and it is genuinely
good at the one job we give it.

**Identity Platform tenants for multi-account.** Rejected: tenants isolate entire user pools,
which is the wrong shape for one human with two accounts.
