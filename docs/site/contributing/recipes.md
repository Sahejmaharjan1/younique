# Recipes

Step-by-step guides for the four most common contributions. Each is designed to be followable
without reading the whole design set.

---

## Recipe 1: Add a connector

**Time:** 1-2 days. **Area:** `connectors/`. **Rules:** `connectors/AGENTS.md`.

### Before you write code

1. **Read the provider's API docs for the approval requirements**, and record them. This is the
   step people skip and then discover eight hours in. Specifically: does production use require
   an app review? Are any scopes "restricted" or "sensitive"? Are there account-type
   restrictions (business-only)? Is there a public API for the thing you want at all?
2. **Open a "new connector" issue** with that information so a maintainer can flag a dead end
   before you invest. Two of the connectors in the original product spec turned out to be
   partly impossible at this step.
3. Create your own OAuth app in the provider's console for development. Every connector supports
   BYO OAuth client, so you never need our credentials.

### Scaffold

```bash
make new-connector key=notion name="Notion"
```

This creates the directory, a manifest stub, a test stub, a cassette directory, and a README
stub.

### Write the manifest (`manifest.py`)

The most important file. Work through it in this order:

1. `auth=` — the OAuth endpoints, PKCE on if supported, `supports_byo_client=True`.
2. `permission_bundles=` — **one bundle per coherent capability**, narrowest scopes that work.
   Write each `description` in plain language: what it can do and what it cannot.
3. For each bundle, set **`produces_untrusted_content`**. `True` for anything returning content
   an outside party could have written. This feeds the taint system that prevents a
   prompt-injected agent from acting autonomously — getting it wrong disables that defence for
   every user. When unsure, set `True`.
4. `grantable_resources=` — what the user picks after OAuth (databases, repos, channels). A
   `lister` function returns them.
5. `platform_status=` — approval requirements and **limitations stated plainly**. This text
   appears in the connect dialog and in the generated docs page.
6. `rate_limits=` — the provider's documented quota and our own conservative per-minute cap.

### Write the tools (`tools/*.py`)

One file per tool. For each:

- Pydantic `Input` with **bounds on every list and string**. These limits are a security control
  against mass exfiltration, not politeness.
- Pydantic `Output`, narrow — return what callers need, not the whole provider response.
- Set `risk=`. Apply the test honestly: is the effect externally visible and not cheaply
  reversible? If yes, it is `high`.
- `summarize_for_approval()` is **required** for `high` risk. Human-readable headline, key
  details, a body preview. A dialog showing raw JSON gets clicked through, which defeats the
  mechanism.
- In `execute()`: `await ctx.require_grant(...)` **first**, before any HTTP. Then `ctx.http`
  (never `httpx` — a lint rule blocks it, because `ctx.http` is what provides SSRF protection).
- Attaching a file? `await ctx.require_artifact_clean(id)` first.

### Health probe (`health.py`)

The cheapest authenticated call that proves the token works. This populates
`connections.health`, which is how a user discovers a dead connection on the Connections page
instead of at 9am on Monday when their report does not arrive.

### Tests

```bash
YOUNIQUE_RECORD=1 pytest connectors/notion/tests/ -k contract   # record cassettes
make scrub-cassettes                                            # strip tokens and emails
pytest connectors/notion/tests/
```

Three tiers, no more: contract (cassettes), error paths (one case per status the provider
returns), grant enforcement (a non-granted resource raises before any HTTP call, asserted with
a strict mock). Do not write live-provider tests or an OAuth E2E.

### README.md

What it does, scopes per bundle and why each is needed, approval status, **limitations stated
plainly**, rate limits, BYO client setup, how to re-record cassettes. The limitations section is
the most valuable part.

### Checklist

- [ ] Manifest validates (`make validate-connectors`)
- [ ] `produces_untrusted_content` correct on every bundle
- [ ] Risk class correct; `summarize_for_approval` on every `high` risk tool
- [ ] No direct `httpx`, `requests`, `socket`, or `subprocess`
- [ ] `require_grant` before every provider call
- [ ] Contract, error-path, and grant tests pass
- [ ] Cassettes scrubbed
- [ ] README with limitations
- [ ] Icon in `packages/ui/icons/`
- [ ] **Nothing outside `connectors/{key}/` changed** (plus the icon)

---

## Recipe 2: Add a model

### A newly released model from an existing provider — 5 minutes

Add an entry to `packages/model-registry/models.yaml`:

```yaml
- provider: anthropic
  model_ref: claude-opus-5
  display_name: Claude Opus 5
  context_window: 500000
  max_output_tokens: 128000
  supports_tools: true
  supports_vision: true
  supports_reasoning: true
  reasoning_control: budget_tokens     # none | boolean | effort | budget_tokens
  status: active
  prices:
    - effective_from: 2026-10-01
      input_micro_usd_per_mtok: 15000000
      output_micro_usd_per_mtok: 75000000
      cached_input_micro_usd_per_mtok: 1500000
```

That is the whole change. The seed upsert is idempotent, so it applies on deploy. Prices are in
**micro-USD per million tokens** — `$15.00 / Mtok` is `15000000`. Get this wrong and every cost
figure for that model is wrong by an order of magnitude, so double-check the decimal places.

`reasoning_control` must match the provider's actual API shape; see
`docs/03-designs/model-registry-and-routing.md` §3 for the four dialects.

### A new provider with a new API shape — 1-2 days

Only needed if the provider is **not** OpenAI-compatible and LiteLLM does not support it. Check
both first; most new providers are one or the other, in which case this is a registry row.

1. Implement `LLMProvider` in `backend/src/younique/llm/providers/{name}.py`: `stream`,
   `complete`, `count_tokens`, `validate_key`.
2. Normalize to the closed `StreamEvent` union. Map reasoning deltas to `ReasoningDelta`, not
   `TextDelta` — they are billed and displayed differently.
3. Map every error to a `ProviderErrorKind`. This table is what makes failures actionable, so
   cover 401, 429 with and without `Retry-After`, 5xx, content filter, and context overflow.
4. Add a `model_providers` seed row with `implementation = "{name}"`.
5. Tests: record a real stream once, commit it as a fixture (scrubbed), and assert the normalized
   `StreamEvent` sequence. Plus the error-mapping table.

---

## Recipe 3: Add an agent tool (not connector-backed)

**Time:** half a day. For platform capabilities rather than third-party services — artifact
manipulation, memory search, invoking a sub-agent.

1. Create `backend/src/younique/agents/tools/{tool}.py` with the same `@tool` decorator and
   Pydantic `Input`/`Output` as a connector tool.
2. Set `risk=`. Same honest test. `younique.delete_artifact` is `medium` (archive is
   reversible); `younique.send_notification` is `low`.
3. Register in `agents/tools/__init__.py`.
4. Add the tool key to the built-in agents' allowlists that should have it. A tool nobody is
   allowed to call does nothing.
5. **Permissions are still checked.** Use `ctx.authorize(action, resource)` — a tool is not a
   permission bypass, and an agent can never exceed its owner's permissions.
6. Test: a deterministic graph test with `FakeChatModel` scripting a call to it, plus a
   permission test asserting an unauthorized principal is refused.

---

## Recipe 4: Add a pipeline node

**Time:** half a day to 2 days depending on the node. **The frontend requires no changes** — the
visual editor renders its form from the JSON Schema the backend serves.

1. Create `backend/src/younique/pipelines/nodes/{category}/{node}.py`.
2. Declare it:

```python
@node(
    type="transform.pivot",
    category="transform",            # source | transform | ai | destination | control
    label="Pivot table",
    inputs={"data": DataFrameRef},
    outputs={"result": DataFrameRef},
    idempotent=True,                 # affects retry safety — be honest
)
class PivotNode(PipelineNode):
    class Params(BaseModel):
        index: list[str] = Field(min_length=1, description="Rows to group by")
        columns: list[str]
        values: str
        aggfunc: Literal["sum", "mean", "count", "min", "max"] = "sum"
```

`description` on each field becomes the form's help text, and `Literal` becomes a select. Write
them for a non-technical user — the retail persona is configuring this.

3. Implement `run(ctx, inputs, params)`. Read with `ctx.read_frame(ref)`, write with
   `ctx.write_frame(df)` — never touch GCS or decide inline-versus-spill yourself.
4. Register in `pipelines/nodes/__init__.py`.
5. **Destination nodes** (anything with an external effect) must set `risk="high"` and
   participate in the approval system, exactly like a connector tool.
6. **`idempotent`** must be honest. It controls whether a retry can safely re-run the node. A
   node that sends email is not idempotent, and claiming otherwise means a retry sends twice.
7. Tests: one happy path with fixture data, one error path, and a round-trip test if the node
   can produce a frame large enough to spill to Parquet.

### Checklist

- [ ] Appears in `GET /v1/node-types` with a complete schema
- [ ] Form renders correctly in the editor (verify locally — no frontend code needed)
- [ ] Field descriptions written for a non-technical user
- [ ] `idempotent` is honest
- [ ] Destination nodes are `risk="high"` and approval-gated
- [ ] Validation errors reference the node, so the editor can highlight it
