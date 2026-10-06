# ADR-0003: SSE over HTTP POST for chat streaming

**Status:** Accepted
**Date:** 2026-10-06

## Context

Chat needs token-by-token streaming with reasoning traces, tool-call events, and approval
interrupts. Runs can suspend for hours awaiting a human, and clients disconnect routinely —
tabs sleep, mobile networks hand off.

## Decision

Server-Sent Events delivered as the response body of an HTTP `POST`. Every event is persisted
to `app.run_events` with a monotonic `seq` **before** it is flushed to the wire, and clients
reconnect to `GET /v1/runs/{id}/events?last_event_id=N` for gap-free resume.

Because the browser `EventSource` API cannot issue a `POST` or set headers, the client reads the
stream with `fetch` plus a `ReadableStream` reader and parses SSE frames itself — roughly 40
lines in `lib/sse.ts`.

## Consequences

**Easier:** authorization is per-request, identical to every other endpoint; cookies and CSRF
work unchanged; no connection state in the load balancer; Cloud Run scaling accounting stays
simple; resume is a plain GET.

**Harder:** we hand-roll the SSE client parser. Any future bidirectional need (collaborative
cursors, live typing indicators) would require a different transport.

**Live with:** a 15-second `ping` keep-alive is mandatory, because the load balancer's stream
idle timeout will close a quiet connection and a reasoning model can think for a long time
before emitting anything.

## Alternatives considered

**WebSocket.** Rejected: it buys bidirectionality we do not need, in exchange for a stateful
connection, our own heartbeat and reconnect-and-resume protocol, per-message authorization
instead of per-request, and more complexity at the load balancer. The upward signals we actually
need — stop and approve — are better as idempotent HTTP calls on their own endpoints, because
they must work from a different device than the one streaming.

**`EventSource` with the token in the query string.** Rejected: putting a credential in a URL
puts it in logs and browser history.

**Long polling.** Rejected: higher latency and more requests for no benefit over SSE.

**In-memory event channels instead of a `run_events` table.** Rejected: it makes resume
impossible across instances, and resume is what enables "close the tab, approve from your phone,
come back to a finished answer" — one of the product's better behaviours.
