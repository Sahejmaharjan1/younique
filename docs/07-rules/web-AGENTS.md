# apps/web/AGENTS.md

Rules for the Next.js frontend. The root `AGENTS.md` applies too.

## The frontend holds no business logic

It renders, routes, and manages local interaction state. Every decision about what a user may
do is made by the backend. Hiding a button is a UX courtesy, **never** a security control —
assume every endpoint will be called directly, because it will be.

## Structure

```
app/              routes ONLY. Thin. Fetch, then delegate to a feature component.
features/{x}/     vertical slice: components, hooks, local state, types for one domain
components/ui/    shadcn primitives. MUST NOT import from features/ or app/.
lib/              api client wiring, sse.ts, formatters, hooks shared across features
```

An import from `components/ui/` into `features/` is correct. The reverse is a lint error — a
primitive that knows about chat is not a primitive.

## Server vs client components

- **Server Component by default.** Add `'use client'` only when you need state, effects, event
  handlers, or browser APIs.
- Initial data for a route is fetched in the Server Component and passed down. Client components
  take over for mutations and live updates.
- The session cookie is forwarded on server-side fetches; use `lib/api/server.ts`, which does it
  correctly.
- Never put a secret, an API key, or anything from `process.env` without the `NEXT_PUBLIC_`
  prefix into a client component.

## Data fetching

- **Every call to our API goes through `packages/api-client`.** A raw `fetch` to our own API
  fails lint, because it bypasses generated types and the shared error handling.
- TanStack Query for server state. Query keys are built by `lib/queryKeys.ts` — never an inline
  array literal, or cache invalidation silently stops working.
- Zustand for genuinely client-only state (composer draft, panel open/closed, pipeline editor
  viewport). Not for server data.
- Optimistic updates for cheap, reversible actions (rename, archive, read-mark). Never for
  anything that spends money or sends a message.

## Streaming

Chat streams over **SSE on a POST**, read with `fetch` plus a `ReadableStream` reader — not
`EventSource`, which cannot set headers or use POST. The parser is `lib/sse.ts`; do not write
another one.

- Persist the last `event.id` and reconnect to
  `GET /v1/runs/{id}/events?last_event_id=N` on disconnect. Dropping tokens on a flaky network
  is the most noticeable possible bug in this product.
- Render reasoning parts in a collapsed disclosure, default collapsed.
- A `ping` event is a keep-alive; ignore it.
- Buffer `part.delta` events with `requestAnimationFrame` batching. Setting React state per
  token drops frames on long responses.
- On `approval.required`, render the approval card inline and stop expecting more events on that
  connection — the run is durably suspended server-side.

## Errors

Every API error is RFC 9457 with a stable `code`. `features/errors/` maps codes to a treatment:

| Shape | Used for |
| --- | --- |
| Inline retry button | `provider_rate_limited`, `provider_timeout`, `provider_unavailable` |
| Offer to switch model | `provider_model_deprecated`, `provider_context_length_exceeded` |
| Link to settings | `provider_invalid_key`, `budget_exceeded`, `quota_exceeded` |
| Reconnect prompt | `connection_needs_reauth`, `connection_revoked` |
| Blocking modal | `consent_required` |
| Re-auth prompt | `reauth_required` |
| Toast | Everything else retryable |
| Error page with `request_id` | `internal_error` |

**Never render a bare "Something went wrong."** If a code has no mapping, show the `detail` plus
the `request_id` with a copy button. An error the user can quote is an error we can fix.

## Accessibility — not optional

`jsx-a11y` runs as **errors**, not warnings.

- Every interactive element is reachable and operable by keyboard. A `div` with `onClick` is a
  lint failure.
- Radix primitives provide focus management and ARIA; do not hand-roll a dialog, menu, or
  combobox.
- Visible focus rings. Never `outline: none` without a replacement.
- Streaming text goes in an `aria-live="polite"` region, announced on completion rather than
  per token.
- The pipeline editor ships a **keyboard-operable list view** of the same DAG. A node canvas
  cannot be made accessible, so the list view is a real alternative, not a fallback — it has the
  same editing capability.
- Charts have a table equivalent behind a toggle.
- Colour never carries meaning alone; status always pairs a colour with an icon or text.

## Performance

- Virtualize any list that can exceed ~100 rows (messages, artifacts, memories, run steps) with
  `@tanstack/react-virtual`.
- Shiki highlighting runs in a Web Worker for blocks over 200 lines.
- `next/image` for all images; artifact thumbnails are generated server-side, never resized in
  the browser.
- Dynamic-import heavy, rarely-used modules: React Flow, PDF.js, the chart library.
- Budget: route JS under 200 KB gzipped, LCP under 2.5 s on a mid-range phone. A Lighthouse CI
  job enforces both.

## Styling

Tailwind v4 with design tokens from `packages/ui/tokens.css`. No arbitrary values for colour,
spacing, or radius — use the token. Dark mode via `class`, and both themes must be checked for
contrast.
