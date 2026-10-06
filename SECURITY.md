# Security

Report vulnerabilities privately through GitHub private vulnerability reporting or by emailing security@younique.dev. We aim to acknowledge within 3 days and to coordinate disclosure within 90 days.

## In scope

The API, web app, connector SDK, session cookies, envelope encryption, authorization, and artifact scanning.

## Out of scope

Social-engineering the account holder into approving a tool call. The approval card shows when an argument was copied from untrusted content, and that human decision remains the last line.

## Residual risk

An injected instruction can still persuade a model to *request* a high-risk tool. The gate turns that into an approval instead of a silent send. A user who sets `allow_when_tainted` on a high-risk tool is warned and must re-authenticate. Reading data is low risk, so grant lists are what limit what can be read at all.

Do not open a public issue for a vulnerability.
