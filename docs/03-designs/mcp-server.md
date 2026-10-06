# MCP: Serving and Consuming

Two independent features that share a protocol:

1. **Serving** — expose Younique's tools, agents, and pipelines so a user can drive them from
   Claude Desktop or any MCP client. (v1)
2. **Consuming** — register an external MCP server as a connector so its tools become available
   to our agents. (v2)

## 1. Serving

### Transport and scope

Streamable HTTP, at `POST /mcp` on the dedicated `mcp` Cloud Run service. Not stdio — that is a
local-process transport and we are a remote service. Not the deprecated HTTP+SSE transport.

What we expose, and why that mapping:

| MCP primitive | Younique concept | Notes |
| --- | --- | --- |
| Tool | A connector tool the token's scopes allow | `gmail.send_email`, `github.create_pr`, and so on |
| Tool | An agent, as `agent.{slug}` | Takes a natural-language `task` and returns the result. Lets Claude delegate a whole multi-step job. |
| Tool | A pipeline, as `pipeline.{slug}` | Takes input bindings, returns the run result |
| Tool | `younique.list_artifacts`, `younique.read_artifact` | Access to the user's files |
| Tool | `younique.search_memory` | Read-only. **Memory writing is never exposed over MCP** — see §1.4. |
| Resource | Artifacts, as `younique://artifact/{id}` | Clean artifacts only |
| Resource | Chats, as `younique://chat/{id}` | Read-only transcripts |
| Prompt | Agent instruction templates | Lets a client offer the user's agents as slash commands |

### OAuth 2.1, per the MCP spec

```mermaid
sequenceDiagram
    participant C as MCP client (Claude)
    participant M as mcp service
    participant A as api / auth
    participant U as User browser

    C->>M: POST /mcp (no token)
    M-->>C: 401 + WWW-Authenticate:<br/>Bearer resource_metadata="/.well-known/oauth-protected-resource"
    C->>M: GET /.well-known/oauth-protected-resource
    M-->>C: {authorization_servers, resource, scopes_supported}  (RFC 9728)
    C->>M: GET /.well-known/oauth-authorization-server
    M-->>C: metadata incl. registration_endpoint  (RFC 8414)
    C->>M: POST /mcp/register {client_name, redirect_uris}
    M-->>C: {client_id}  (RFC 7591 dynamic registration)
    C->>U: open /mcp/authorize?client_id&code_challenge&scope&resource
    U->>A: authenticate with the normal session; CONSENT SCREEN
    Note over U,A: User picks exactly which tools,<br/>agents, pipelines, and connections<br/>this client may use.
    U-->>C: redirect with code
    C->>M: POST /mcp/token {code, code_verifier}
    M-->>C: {access_token (1 h), refresh_token}
    C->>M: POST /mcp with Authorization: Bearer
    M-->>C: tools/list filtered by the token's scopes
```

Requirements the spec imposes that are easy to get wrong, each with a test:

| Requirement | Implementation |
| --- | --- |
| PKCE mandatory, S256 only | `plain` is rejected. A missing `code_challenge` is rejected. |
| Dynamic client registration | RFC 7591, rate-limited per IP, with registrations expiring after 90 days unused |
| **Audience binding** | Tokens carry the `resource` they were issued for and are rejected if presented elsewhere. This is what prevents a confused-deputy attack where a token for another MCP server is replayed at ours. |
| Exact redirect-URI matching | No wildcards, no prefix matching. Loopback (`http://127.0.0.1:*`) is the single exception, as the spec allows for native clients. |
| Short-lived access tokens with rotating refresh | 1 h access, refresh rotated on use with the old one invalidated |
| Resource metadata discovery | Both well-known documents served with CORS, since clients fetch them from arbitrary origins |

### Scoped tokens

`app.mcp_tokens` stores the hash, scopes, and — crucially — a `tool_allowlist` chosen by the
user on the consent screen.

```
mcp:tools:read            list tools
mcp:tools:execute         call tools (intersected with tool_allowlist)
mcp:agents:execute        run agents
mcp:pipelines:execute     run pipelines
mcp:artifacts:read
mcp:memory:read
```

Effective permissions are the **intersection** of: the token's scopes, the token's
`tool_allowlist`, the user's workspace role, the connection grants on each connection, and the
tool policies. Five narrowing layers, never widening. `tools/list` returns only what passes all
five, so an MCP client never sees a tool it cannot call — which is both a better experience and
a smaller attack surface.

### Approvals over MCP

The hardest part of this feature, and the place where a naive implementation becomes a security
hole.

An MCP client is not a browser; it cannot render our approval UI. The temptation is to treat
MCP calls as pre-approved, which would make MCP a complete bypass of the approval system. We
do not.

```
Client calls gmail.send_email
  ↓
policy_gate: ask_each_time (or the run is tainted)
  ↓
Return an MCP tool result, NOT an error:
  {
    "content": [{ "type": "text", "text":
      "Approval required to send this email. Approve at:
       https://younique.dev/approvals/0193abc  (expires in 24h)" }],
    "isError": false,
    "_meta": { "younique/approval_id": "0193abc",
               "younique/status": "pending_approval" }
  }
  ↓
The user approves in the browser (or the Younique mobile notification)
  ↓
Client calls younique.check_approval(approval_id) — or retries the original call,
which now finds an approved decision and executes
```

The model in the client reads the text, tells the user to approve, and waits. It works with
every MCP client because it uses only the content channel, and no client needs special support.
`_meta` lets a future Younique-aware client render something nicer.

Tool policies set to `always_allow` still apply, so a user who has decided a tool is safe is
not re-prompted. Taint-based gating also still applies, which matters: a tool that reads an
email then one that sends an email, called in sequence by an MCP client, hits the same
capability gate as it would in our own agent.

### What is never exposed over MCP

| Not exposed | Reason |
| --- | --- |
| Provider API keys, connector tokens | Never leave the backend, for anyone |
| Memory **writes** | A remote client writing durable memory is a persistent prompt-injection vector with no human in the loop |
| Connection management (create, revoke, re-scope) | Privilege escalation. Must be a browser action with a session. |
| Tool policy changes | Same — a client could grant itself `always_allow` |
| Workspace or member administration | Same |
| Other users' resources | Tokens are user-scoped, enforced by `authorize()` |
| Audit log | Reading the security log through an API-key-like credential is itself a risk |

Because `authorize()` is the same chokepoint ([authorization doc](authorization-and-sharing.md)),
these are not a denylist maintained by hand — an MCP principal simply lacks the actions, and the
denylist above is documentation of that fact rather than its implementation.

### Token management UI

`GET /v1/mcp-tokens` lists every connected client with its name, scopes, selected tools,
`last_used_at`, and creation date, with one-click revocation. Revocation is immediate. Every
MCP tool execution writes an audit event with the client as actor, so "what has Claude been
doing with my account" is a concrete, answerable question.

## 2. Consuming external MCP servers (v2)

An external MCP server registers as a connection with `connector_key = 'mcp'`:

```python
MANIFEST = ConnectorManifest(
    key="mcp",
    display_name="MCP Server",
    auth=UserConfigured(fields=["server_url", "auth_kind", "credentials"]),
    dynamic_tools=True,       # discovered at connect time, not declared
    platform_status=PlatformStatus(approval_required=False),
)
```

Discovery calls `tools/list` and caches each tool's name, description, and input schema into
`connection_tools`. The schema becomes the LLM-facing tool definition, so an external server's
tools are indistinguishable from first-party ones at the agent level.

### Trust posture

An external MCP server is **less** trusted than a first-party connector, and the design says so
explicitly:

| Control | Rule |
| --- | --- |
| Taint | Every result is `untrusted`. Always. No exceptions and no per-server override. |
| Default policy | Every discovered tool defaults to `ask_each_time`. The user can relax it per tool after seeing what it does. |
| **Rug-pull detection** | Tool names, descriptions, and schemas are hashed at approval time. If a hash changes, the tool is **disabled** and requires explicit re-approval showing a diff. A malicious server that changes a benign tool's description after approval — injecting instructions into the description the model reads — is a documented MCP attack, and this is the defence. |
| Egress | The server URL goes through the SSRF-safe client: resolved-IP checks against private and link-local ranges before connect and after every redirect, HTTPS required except for explicit `localhost`. |
| Name collision | External tools are namespaced `mcp.{connection_slug}.{tool}`, so a server cannot shadow `gmail.send_email`. |
| Prompt-injection surface | Tool descriptions from an external server are placed in a delimited, provenance-tagged block, never concatenated into our system prompt. |
| Resource limits | 30 s per call, 256 KB result cap, 30 calls per minute per connection |
| Credentials | Stored with the same envelope encryption as any connector token |

The rug-pull control is worth the implementation cost. Tool descriptions are read by the model
as authoritative, so a server that can change them after approval can retroactively instruct
the agent, and nothing else in the pipeline would notice.

## 3. Testing

| Test | Proves |
| --- | --- |
| Full OAuth 2.1 flow against a reference client | Discovery, dynamic registration, PKCE, code exchange, refresh rotation |
| PKCE enforcement | `plain` and missing challenge are rejected |
| Audience binding | A token issued for a different `resource` is rejected |
| Redirect-URI exactness | A wildcard or prefix-matched URI is rejected; loopback is allowed |
| Scope intersection | `tools/list` returns the intersection of all five narrowing layers, asserted across a matrix of scope and role combinations |
| Approval over MCP | A gated tool returns a pending-approval content result, does not execute, and executes on retry after approval |
| No bypass | An MCP principal is denied every action in the "never exposed" table |
| Revocation | A revoked token fails on the next call, with no cache |
| Rug-pull | A changed tool schema disables the tool and requires re-approval |
| SSRF | Registering `http://169.254.169.254/` or a DNS name resolving to a private range is refused |
| Taint propagation | An external MCP result taints the run and gates a subsequent high-risk tool |

**Not tested:** compatibility with every MCP client in existence. We test against the official
MCP Inspector and one real client (Claude Desktop) in a manual pre-release check, and document
which clients are verified.
