# 06 — Frontend Architecture

## 1. UX principles

These resolve design arguments the way the architectural principles resolve technical ones.

1. **Never surprise the user with an action.** Anything externally visible and not cheaply
   reversible shows a human-readable summary and waits. This is a product principle before it is
   a security one.
2. **Always show what the agent knows and did.** Which memories were retrieved, which files were
   read, which tools ran, what each one returned, what it cost. Opacity is the main reason people
   abandon agent products.
3. **Errors name the fix.** Every recoverable error renders an action button, not an apology.
   A bare "Something went wrong" is a bug report against the frontend.
4. **Visual where visual helps, textual where it does not.** Pipeline graphs, run timelines, and
   usage charts earn their complexity. A settings page does not need a diagram.
5. **Keyboard-complete.** Every flow is operable without a mouse, including the pipeline editor
   (via its list view). `jsx-a11y` runs as errors.
6. **Optimistic only when reversible.** Rename, archive, mark-read — yes. Sending a message,
   spending money, publishing a post — never.
7. **Progressive disclosure.** A non-technical user sees a chat box. A developer finds the raw
   tool arguments, the token counts, and the trace link one click deeper. Both are first-class;
   neither pays for the other.

## 2. Route map

```
(marketing)/                      public, static, no session
  /                               landing
  /legal/terms/[version]          versioned — a share link to v2 must keep working
  /legal/privacy/[version]

(auth)/
  /login  /signup                 Firebase providers + email
  /consent                        blocking; served on 409 consent_required
  /onboarding                     3 steps: add a key, connect a service, first chat

(app)/                            authenticated shell: sidebar + workspace switcher
  /                               → /chat/new
  /chat/new  /chat/[chatId]       the product's centre of gravity
  /artifacts                      ?origin&mime_group&from&to&q&status
  /artifacts/[artifactId]         detail, version history, preview
  /connections                    catalogue + connected list with health
  /connections/[connectionId]     bundles, granted resources, activity, revoke
  /agents  /agents/new  /agents/[agentId]
  /agents/[agentId]/runs/[runId]  run detail with the step inspector
  /pipelines  /pipelines/[id]     editor (React Flow) + list view toggle
  /pipelines/[id]/runs/[runId]    live visual run monitor
  /approvals                      inbox
  /memory                         manager, grouped by set
  /usage                          ?group_by=day|model|agent|pipeline|chat
  /settings/profile  /models  /keys  /security  /sessions  /workspace
  /settings/workspace/members  /budgets  /tool-policies  /audit
  /settings/mcp                   connected MCP clients and tokens

share/[token]                     public read-only; no session; noindex

api/                              ONLY: auth cookie exchange, OTel proxy, nothing else
```

`app/api/` is deliberately almost empty. Route handlers are a tempting place to put logic, and
logic there is logic the backend cannot enforce. The two exceptions exist because they must run
on our origin: the Firebase-token-to-cookie exchange (so the cookie is `__Host-` scoped) and an
OTel collector proxy (so browser traces are not blocked by CORS).

## 3. State and data

| Concern | Tool | Rule |
| --- | --- | --- |
| Initial route data | Server Components | Fetched server-side, passed as props. Fast first paint, no loading spinner on navigation. |
| Server state | TanStack Query | Keys built by `lib/queryKeys.ts` — never an inline array, or invalidation silently stops working |
| Streaming | `fetch` + `ReadableStream`, parsed by `lib/sse.ts` | Not `EventSource` (cannot POST or set headers). One parser, reused. |
| Client-only state | Zustand, one small store per concern | Composer draft, panel state, editor viewport. Never server data. |
| Forms | React Hook Form + Zod, schemas generated from OpenAPI | One validation definition shared with the backend |
| Mutations | `openapi-fetch` through `packages/api-client` | A raw `fetch` to our API fails lint |

### Streaming in practice

The chat is the hardest component in the app, and three details make or break it:

**Delta batching.** Setting React state per token drops frames on a long response. Deltas
accumulate in a ref and flush on `requestAnimationFrame`.

**Resume on reconnect.** The last `event.id` is persisted; on disconnect the client reconnects
to `GET /v1/runs/{id}/events?last_event_id=N`. Losing tokens to a sleeping tab or a mobile
handoff is the most noticeable possible bug in this product, and the server-side `run_events`
table exists specifically so the client can be naive about it.

**Approval terminates the stream.** On `approval.required` the run is durably suspended
server-side, so the client renders the approval card and stops expecting events. After a
decision it reconnects to the resume endpoint. The user can close the tab, approve from their
phone, and come back to a completed answer.

## 4. Component library

shadcn/ui — source vendored into `components/ui/`, not a dependency — over Radix primitives and
Tailwind v4. Radix is the load-bearing choice: focus management, ARIA wiring, and typeahead in
menus and comboboxes are the things hand-rolled components always get wrong, and they are the
difference between passing an accessibility audit and claiming to.

```
packages/ui/              shared across apps; tokens.css is the only source of design values
apps/web/components/ui/   shadcn primitives; MUST NOT import from features/
apps/web/features/{x}/    vertical slices — components, hooks, types for one domain
```

The import rule is enforced by lint: `ui → features` is an error. A primitive that knows about
chat is not a primitive.

| Library | Use | Loading |
| --- | --- | --- |
| Shiki | Code highlighting | Web Worker for blocks over 200 lines |
| React Flow (xyflow) | Pipeline editor and run monitor | Dynamic import — it is large and used on two routes |
| PDF.js | PDF preview | Dynamic import, inside a sandboxed iframe |
| Recharts | Usage charts | Dynamic import |
| `@tanstack/react-virtual` | Every list over ~100 rows | Static |
| DOMPurify | SVG and HTML artifact sanitization | Static |

## 5. Key screens

### Chat — `/chat/[chatId]`

```
┌────────────┬──────────────────────────────────────────┬───────────────┐
│ Sidebar    │ Header: title · model picker · reasoning │ Context panel │
│            │   toggle · cost · share · ⋯              │  (collapsible)│
│ workspace  ├──────────────────────────────────────────┤               │
│  switcher  │                                          │ Files (4)     │
│            │  [user] Send the Q3 report to ops@…      │  q3.xlsx      │
│ + New chat │                                          │  chart.png    │
│            │  [assistant]                             │               │
│ Chats      │   ▸ Reasoning (1.2k tokens)   collapsed  │ Memory used(3)│
│  Today     │   I'll send that now.                    │  • GBP prices │
│  Yesterday │   ┌────────────────────────────────────┐ │  • concise    │
│  …         │   │ ⚠ Approve: Send email              │ │               │
│            │   │ To: ops@acme.com                   │ │ Tools (2)     │
│ Agents     │   │ Subject: Q3 report                 │ │  sheets.read  │
│ Pipelines  │   │ Attachments: 1 (q3.xlsx)           │ │  gmail.send   │
│ Artifacts  │   │ ⓘ Recipient came from the email    │ │               │
│ Memory     │   │   this agent just read             │ │ Cost $0.043   │
│ Usage      │   │ [Approve] [Reject] [Always allow]  │ │               │
│            │   └────────────────────────────────────┘ │               │
│ Approvals 2│                                          │               │
├────────────┤  ┌─────────────────────────────────────┐ │               │
│ account ▾  │  │ Message…         📎  ⏹ Stop  ↑ Send │ │               │
└────────────┴──┴─────────────────────────────────────┴─┴───────────────┘
```

Details that matter: reasoning is collapsed by default with a token count (so the cost is
visible without the text); the context panel makes "what does it know" answerable at a glance,
satisfying principle 2; the provenance line on the approval card (`ⓘ Recipient came from the
email this agent just read`) is the small feature that lets a human catch a prompt injection;
and cost is in the header, not buried in settings, because that is where the decision to turn
off reasoning gets made.

### Pipeline editor — `/pipelines/[id]`

React Flow canvas with a palette on the left (from `GET /v1/node-types`), a parameter form on
the right generated from the selected node's JSON Schema, validation errors pinned to the
offending node, and a **list view toggle** in the header.

The list view is not a degraded fallback. A node canvas cannot be made keyboard-accessible, and
some users simply prefer an outline; it presents the same DAG as a nested, fully operable tree
with identical editing capability. Treating it as a first-class view is the only honest way to
meet the accessibility requirement here.

Run mode reuses the same layout with nodes coloured by status and edges animated, driven by the
run's SSE stream. A failed node offers "retry from here", which seeds a new run with the prior
run's upstream outputs — the feature that turns pipeline debugging from minutes into seconds.

### Artifacts — `/artifacts`

Three views over one query: type-aware cards with thumbnails, a dense table for bulk actions,
and a timeline grouped by day. Filters are URL state, so a filtered view is shareable and
survives a refresh. Every card links back to the chat or run that produced it, because "where
did this file come from" is the most common question about a file.

### Memory manager — `/memory`

Grouped by set, with each memory showing kind, importance, source, last used, and use count.
Extracted memories carry an "inferred" badge with a link to the originating message until the
user confirms or edits. Conflicting pairs surface as a resolution card ("You previously told me
X; now you've said Y") with keep-both / keep-new / keep-old. Version history has a diff view and
restore.

### Usage — `/usage`

Stacked area of daily cost by model with budget lines overlaid, plus tables by model, by agent
and pipeline, and by chat. Every chart has a table equivalent behind a toggle. Currency shows 4
decimal places below $1 — `$0.00` for a real cost makes a dashboard look broken.

### Connections — `/connections`

The catalogue shows **limitations before connecting**, read from the connector manifest. The
Instagram card says "Business and Creator accounts only — personal accounts have no API" in the
card itself, not after a failed connection. The connect flow is: pick permission bundles
(checkboxes with plain-language descriptions and risk badges) → OAuth → pick resources (nothing
selected by default) → done.

### Account switcher

A sidebar footer menu listing **workspaces first** (one identity, different contexts — what most
users actually want) and signed-in identities second, with "Add another account" below. Each
identity row shows its email and avatar. Switching workspace is a header change; switching
identity sets `X-Account-Id`. The distinction is explained inline, once, because conflating them
is the most common user confusion in multi-tenant products.

## 6. Error handling

`features/errors/` maps every `code` from the [API taxonomy](05-api-design.md) to one treatment:

| Treatment | Codes |
| --- | --- |
| Inline retry | `provider_rate_limited`, `provider_timeout`, `provider_unavailable` |
| Switch-model offer | `provider_model_deprecated`, `provider_context_length_exceeded` |
| Link to settings | `provider_invalid_key`, `budget_exceeded`, `quota_exceeded` |
| Reconnect prompt | `connection_needs_reauth`, `connection_revoked` |
| Blocking modal | `consent_required` |
| Re-auth prompt | `reauth_required` |
| Explanatory inline card | `tool_blocked_by_policy`, `tool_blocked_by_taint`, `artifact_not_clean` |
| Toast | Other retryable errors |
| Error page with a copyable `request_id` | `internal_error` |

An unmapped code renders the server's `detail` plus the `request_id` with a copy button. A
`request_id` a user can paste is an error we can find in Cloud Trace in seconds.

## 7. Performance budgets

Enforced by Lighthouse CI on `web` PRs; a regression fails the build.

| Metric | Budget |
| --- | --- |
| Route JS, gzipped | 200 KB |
| LCP, mid-range mobile | 2.5 s |
| INP | 200 ms |
| Chat first token, p95 | 2 s excluding provider time |
| Streaming frame rate | 60 fps during token streaming |
| Message list | Virtualized above 100 messages |

## 8. Testing

Playwright for the critical flows in [10-testing-strategy.md](10-testing-strategy.md) §2, with
LLM and provider responses mocked at the network boundary. Vitest plus Testing Library for
pure logic: the SSE parser, the error map, formatters, and the query-key builders.

**Not tested:** visual regression, component snapshots, React Flow canvas interaction, or
anything Radix already tests. Those churn on every design change and catch almost nothing real.
