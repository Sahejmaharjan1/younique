# connectors/AGENTS.md

Rules for `connectors/`. The root `AGENTS.md` applies too. Design:
`docs/03-designs/connector-framework.md`. Step-by-step: `docs/07-rules/recipes.md`.

## The contract

A connector is **self-contained**. One directory containing a manifest, tools, a client, a
health probe, cassettes, tests, and a README. Adding one must require **zero changes** outside
`connectors/{key}/` and, if it needs an icon, `packages/ui/icons/`.

If your connector needs a change in `backend/src/younique/agents/` or `apps/web/`, that is a
gap in the framework — open an issue about the framework instead of working around it.

## Forbidden imports

```python
import httpx       # NO
import requests    # NO
import socket      # NO
import subprocess  # NO
```

A lint rule blocks these inside `connectors/*/`. Use `ctx.http`, which provides SSRF
protection (resolved-IP checks against private and link-local ranges, before connect and after
every redirect), per-connector rate limiting, timeouts, and retry. Reaching for `httpx`
directly bypasses all of it — most importantly the metadata-endpoint protection.

## Permission bundles, not a scope blob

Declare one bundle per coherent capability, each with its own scopes and tools:

```python
PermissionBundle(
    key="send",
    display_name="Send email",
    description="Send email as you. Cannot read your mailbox.",   # plain language
    scopes=["https://www.googleapis.com/auth/gmail.send"],
    tools=["gmail.send_email"],
    risk="high",
    produces_untrusted_content=False,
)
```

Rules:

- **Request the narrowest scope that works**, even if it is less convenient. Prefer
  `drive.file` (per-file, non-restricted) over `drive.readonly` (restricted, requires an annual
  third-party security assessment). This trade is almost always worth making.
- A user who selects only `send` gets a connection whose read tools **do not exist**. That is
  the design — absence, not restriction.
- `description` is user-facing. Write what it can and cannot do, in one sentence.

## `produces_untrusted_content` — get this right

Set it `True` on **any** bundle whose tools return content an outside party could have
influenced: email bodies, calendar invite text, Slack messages, GitHub issue and PR bodies,
fetched web pages, file contents, external MCP results.

Getting this wrong is the most consequential mistake a connector author can make. It is the
input to the taint system, which is what prevents a prompt-injected agent from autonomously
sending email or merging a PR. A read tool whose bundle says `False` silently disables the
primary defence for every user of that connector.

When in doubt, set it `True`. The cost is an extra approval prompt. The cost of the other
mistake is a user's mailbox exfiltrated.

## Risk classes

| Risk | Criterion | Default policy |
| --- | --- | --- |
| `low` | Read-only, no side effects | `always_allow` |
| `medium` | Creates or modifies something reversible (draft, comment, sheet cell) | `ask_each_time` |
| `high` | Externally visible and **not cheaply reversible**: send email, merge PR, publish post, delete, pay | `ask_each_time`, and `always_allow` is overridden when tainted |

"Externally visible and not cheaply reversible" is the test. Apply it honestly — classifying a
send as `medium` to reduce friction is a security regression.

Every `high` risk tool **must** implement `summarize_for_approval()`, returning a human-readable
headline, key-value details, a body preview, and an `irreversible` flag. A test enforces this.

## Granular grants

Provider scopes are the ceiling; `connection_grants` is the policy. Call
`ctx.require_grant(kind, ref, action)` **before** the provider request, every time.

```python
async def execute(self, ctx, inp):
    await ctx.require_grant("repo", inp.repo, "create_pr")   # before any HTTP
    ...
```

- Default is **nothing granted**. The user selects explicitly. Defaulting to "all" makes the
  feature theatre.
- Where the provider offers a genuinely narrower credential, use it. GitHub **App** installation
  tokens are repo-scoped by the platform, so the GitHub connector uses an App rather than an
  OAuth app, and `require_grant` becomes defence in depth.
- A failed grant check is a **security audit event**, not just an error — in practice it means a
  confused model or an injection attempt.

## Input validation

Bound everything. These limits are a security control, not politeness:

```python
to: list[EmailStr] = Field(max_length=25)
attachment_artifact_ids: list[UUID] = Field(default_factory=list, max_length=10)
body_markdown: str = Field(max_length=100_000)
```

A prompt-injected agent attempting mass exfiltration should fail validation before a request
leaves the process.

## Errors

Raise `ConnectorError` subclasses from `_sdk/errors.py`. Map every status the provider actually
returns: 401 → `ConnectionNeedsReauth`, 403 → `ConnectorPermissionDenied`, 404 →
`ConnectorResourceNotFound`, 429 → `ConnectorRateLimited` (carry `Retry-After`), 5xx →
`ConnectorUnavailable`.

Never let a provider SDK exception propagate. They routinely include the request, and the
request includes the `Authorization` header.

## Artifacts

- Attaching a file: `await ctx.require_artifact_clean(artifact_id)` first. An unscanned or
  infected artifact must never be sent anywhere.
- Producing a file: `await ctx.emit_artifact(...)`. Do not write to GCS yourself.

## Tests — three tiers, no more

1. **Contract.** Cassettes replayed with `respx` in strict mode. Assert request shape, response
   parsing, and pagination. Record with `YOUNIQUE_RECORD=1`; the scrubber strips tokens and
   emails; CI fails if a cassette matches a secret pattern.
2. **Error paths.** One case per error the provider actually returns, including 429 with and
   without `Retry-After`, and a malformed body. This tier finds more real bugs than the happy
   path, because you already ran the happy path by hand.
3. **Grant enforcement.** A tool called with a non-granted resource raises **before** any HTTP
   request. Assert with a strict mock that fails on any unexpected call.

Do **not** write: live provider calls, a full OAuth redirect E2E (one generic test covers the
framework), or exhaustive field mapping of every response attribute.

## README.md — required

Every connector ships one, covering: what it does, scopes per bundle and why each is needed,
**platform approval status and what it requires**, known limitations stated plainly (for
example "Instagram: business and creator accounts only; personal accounts have no API since
Meta deprecated Basic Display in December 2024"), rate limits, how to set up a BYO OAuth client,
and how to record cassettes.

The limitations section is the most important part. A user discovering a limitation after
connecting is a support ticket and a trust problem; the same fact in the connect dialog is just
information.
