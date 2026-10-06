# ADR-0010: AGPL-3.0 core, Apache-2.0 SDK edges, DCO

**Status:** Accepted
**Date:** 2026-10-06

## Context

The project is open source and also intends to offer a hosted deployment. The main commercial
risk to an open-source infrastructure project is a well-funded party taking the code, running it
as a closed service, and contributing nothing back. The main *community* risk is a license or
contribution process that deters people from participating.

These pull in opposite directions, and the resolution depends on which part of the codebase you
are talking about.

## Decision

- **Core: AGPL-3.0-only.** The server-side-use provision means anyone offering Younique as a
  network service must publish their modifications.
- **`packages/api-client`, `packages/sdk`, `connectors/_sdk`: Apache-2.0.** Nobody should have
  to AGPL their own application to call our API, nor to publish a connector.
- **Docs: CC-BY-4.0.**
- **Contributions: DCO** (`Signed-off-by`), enforced in CI. No CLA.
- SPDX headers on every file, verified by `reuse lint`.

## Consequences

**Easier:** a closed SaaS fork is legally obliged to contribute back; copyright stays distributed
among contributors under DCO, which keeps a future dual-licensing option genuinely open;
contributing is a `git commit -s` away.

**Harder:** some companies have blanket AGPL prohibitions and will not adopt or contribute. Some
contributors are confused by multi-license repositories, which is why the boundary follows
directory lines exactly and is stated in `CONTRIBUTING.md`.

**Live with:** the AGPL/Apache boundary must be respected in imports. An AGPL file imported into
`packages/sdk` would silently contaminate the permissive edge, so `reuse lint` plus a dependency
direction check in CI guards it.

## Alternatives considered

**Apache-2.0 throughout.** Maximum adoption and the friendliest to corporate contributors.
Rejected: zero protection against closed reselling, which for a project whose hosted version is
the sustainability plan is the one risk worth insuring against.

**AGPL-3.0 with a CLA.** Rejected: a CLA gives relicensing flexibility, but it measurably
deters drive-by contributors — the exact population a new project depends on. DCO achieves
provenance without asking anyone to sign a legal agreement to fix a typo.

**BSL or an Elastic-style source-available license.** Rejected: not OSI-approved open source, and
the brief specifies an open-source project. These licenses also reliably generate community
hostility that outweighs their commercial protection at this stage.

**MIT.** Rejected for the same reason as Apache-2.0, with less patent clarity.
