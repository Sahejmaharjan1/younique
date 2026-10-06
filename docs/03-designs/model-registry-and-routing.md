# Model Registry and Provider Routing

Requirement: "users can choose any model per chat, including models that do not exist yet,
without a redeploy." That decomposes into three things — a registry that is data, an interface
that hides provider differences, and an error taxonomy that makes failures actionable.

## 1. The registry is rows, not code

`app.models` and `app.model_prices` ([04 §2.3](../04-database-schema.md)) hold the catalogue.
Three write paths:

1. **Seed file.** `packages/model-registry/models.yaml` is the version-controlled source of
   truth for public models. An idempotent upsert runs on deploy. A community PR adding a
   newly-released model touches exactly one YAML file and needs no Python.
2. **Admin API.** `POST /v1/models` with the admin role, for adding a model between releases.
   This is the "no redeploy" path.
3. **Workspace-private models.** Any user can register an OpenAI-compatible endpoint
   (`base_url` plus a key), which covers local Ollama, vLLM, LM Studio, OpenRouter, Azure
   OpenAI, Bedrock proxies, and anything else that speaks the OpenAI wire format.
   `models.workspace_id` is non-null for these, and `NULL` means global.

```yaml
# packages/model-registry/models.yaml
- provider: anthropic
  model_ref: claude-sonnet-4-5
  display_name: Claude Sonnet 4.5
  context_window: 200000
  max_output_tokens: 64000
  supports_tools: true
  supports_vision: true
  supports_reasoning: true
  reasoning_control: budget_tokens        # none | boolean | effort | budget_tokens
  supports_prompt_cache: true
  status: active
  prices:
    - effective_from: 2026-01-01
      input_micro_usd_per_mtok: 3000000
      output_micro_usd_per_mtok: 15000000
      cached_input_micro_usd_per_mtok: 300000
  capabilities:
    parallel_tool_calls: true
    json_schema_output: true
    max_tool_count: 128
```

`GET /v1/models?available=true` returns only models the workspace holds a valid key for, which
is what the chat model picker renders. Showing a model a user cannot use is a dead end, so the
default list is filtered and an "all models" toggle explains what is missing and links to the
key settings.

### Lifecycle statuses

| Status | Behaviour |
| --- | --- |
| `active` | Selectable, default-visible |
| `preview` | Selectable behind a "preview" badge; excluded from fallback chains |
| `deprecated` | Still works; the picker shows a warning and `replacement_model_id`; existing chats keep working |
| `retired` | Provider has removed it. Calls fail fast with `provider_model_deprecated` and the remediation offers the replacement. Chats pinned to it are switched on the user's confirmation, never silently. |

## 2. The provider interface

```python
class LLMProvider(Protocol):
    async def stream(self, req: CompletionRequest) -> AsyncIterator[StreamEvent]: ...
    async def complete(self, req: CompletionRequest) -> Completion: ...
    async def count_tokens(self, req: CompletionRequest) -> int: ...
    async def validate_key(self, key: SecretStr, base_url: str | None) -> KeyStatus: ...
```

`StreamEvent` is a closed union, deliberately small:

```python
StreamEvent = (
    ReasoningDelta(text)            # thinking tokens
  | TextDelta(text)
  | ToolCallStart(id, name)
  | ToolCallArgsDelta(id, json_fragment)
  | ToolCallEnd(id)
  | Usage(input, cached_input, output, reasoning)
  | Finish(reason: "stop"|"length"|"tool_calls"|"content_filter"|"error")
  | ProviderError(ProviderErrorKind, retry_after_ms, raw_safe)
)
```

### LiteLLM as the default implementation, with native escape hatches

LiteLLM normalizes 100+ providers' streaming, tool-calling, and reasoning parameters, which is
an enormous amount of work we do not want to own. The honest risk is that any such abstraction
lags the frontier: Anthropic's extended thinking with interleaved tool use, OpenAI's Responses
API with server-side state, and provider-specific prompt caching controls are exactly the
features that differentiate a good agent product and exactly the features a normalizing layer
smooths over or delays.

**Resolution:** our own `LLMProvider` interface is the contract. `LiteLLMProvider` is the
default implementation and handles the long tail. `AnthropicProvider` and `OpenAIProvider` are
native implementations used for those two providers, selected by
`model_providers.implementation`. Switching a provider between native and LiteLLM is a database
value, so if LiteLLM ships support for a feature we hand-rolled, we drop back to it without a
code change in the agent runtime.

Rejected alternatives: LangChain chat models (couples the whole runtime to LangChain's
abstraction and release cadence, and we only want LangGraph); routing everything through
OpenRouter (contradicts the BYOK privacy promise — the user's prompts would traverse a third
party); hand-rolling all providers (unbounded maintenance for the long tail).

## 3. Reasoning: one toggle, four provider dialects

Providers express "think harder" four incompatible ways. `models.reasoning_control` records
which dialect a model speaks, and one function translates:

| `reasoning_control` | Provider API shape | Our mapping from `off / low / medium / high` |
| --- | --- | --- |
| `none` | Not supported | Parameter omitted; the UI hides the toggle for this model |
| `boolean` | A flag | `off` → false, anything else → true |
| `effort` | `reasoning_effort: "low"\|"medium"\|"high"` | Direct, with `off` omitting the parameter |
| `budget_tokens` | A thinking token budget | `low` → 2048, `medium` → 8192, `high` → 24576, clamped to `max_output_tokens - 1024` |

Resolution order for whether reasoning is on: per-chat `reasoning_mode` → per-agent
`reasoning_mode` → user default → `off`. `inherit` at any level defers to the next.

Display is a separate concern from generation. Reasoning text streams as
`message_parts` rows with `kind = 'reasoning'`, so:

- The chat UI can collapse or hide them without a second request.
- A retention policy can `DELETE WHERE kind = 'reasoning'` after N days.
- Share links exclude them by default ([authorization doc §6](authorization-and-sharing.md)),
  because reasoning traces are consistently more candid than final answers.
- Reasoning tokens are billed separately in `usage_events.reasoning_tokens`, which matters
  because they are often the dominant cost on a reasoning model and users are startled by it.

Providers that return **redacted or encrypted** thinking blocks (Anthropic does this for safety
reasons) are stored verbatim in `message_parts.data` and displayed as "reasoning hidden by
provider". They must be passed back unmodified on the next turn or the provider rejects the
request, so the storage is opaque by design — a transformation here would break multi-turn
reasoning, and that is noted in the backend rules file.

## 4. Error mapping

Each provider's errors normalize to `ProviderErrorKind`, which is what the
[API error taxonomy](../05-api-design.md) surfaces:

| Kind | Typical triggers | Retry | Fallback |
| --- | --- | --- | --- |
| `rate_limited` | 429, `overloaded_error` | Honour `Retry-After`, else backoff from 1 s, 3 attempts, full jitter | Yes, after retries |
| `timeout` | Connect or read timeout, 504 | 2 attempts | Yes |
| `unavailable` | 500, 502, 503 | 2 attempts | Yes |
| `invalid_key` | 401, 403 `authentication_error` | Never | No — mark the key `invalid`, pause dependent schedules, notify |
| `insufficient_quota` | 429 `insufficient_quota`, billing errors | Never | Yes, to a different provider |
| `content_filtered` | `content_filter` finish reason, 400 safety refusal | Never | No — surface the provider's reason verbatim |
| `context_length_exceeded` | 400 on token count | Once, after trimming memory and the oldest turns | No |
| `model_not_found` | 404 | Never | Yes, to `replacement_model_id` |
| `bad_request` | Malformed tool schema, unsupported parameter | Never | No — this is our bug; log at `error` and alert |
| `stream_interrupted` | Connection dropped mid-stream | Never | No — **persist the partial output** |

Two behaviours worth stating as rules rather than defaults.

**Never silently retry a content filter.** Retrying with a modified prompt to get around a
provider's safety system is both a terms violation and dishonest to the user. We show what the
provider said and stop.

**Never discard a partial stream.** The tokens were generated and billed. The partial
assistant message is persisted with `status = 'stopped'` and an error part, and the UI offers
"continue" (a new turn seeded with the partial) rather than throwing the work away. This is
also why usage is recorded from the `Usage` event *or* reconstructed from token counts on
interruption, never only on success.

## 5. Fallback chains

A chat or agent can define an ordered fallback list. Rules that keep it from becoming a
surprise:

1. Fallback only triggers on `rate_limited`, `timeout`, `unavailable`, `insufficient_quota`, or
   `model_not_found`. Never on `content_filtered`, `invalid_key`, or `bad_request`.
2. The fallback model must satisfy the run's requirements — if the agent needs tools, a
   non-tool model is skipped rather than attempted.
3. **The user is told, in the transcript.** A `message_parts` row with
   `kind = 'error'`, severity `info`: "Claude Sonnet 4.5 was rate-limited; continued with GPT-5."
   Silently changing the model that answered is the kind of thing that destroys trust in an
   agent product, and the cost difference may be significant.
4. Fallback never crosses a reasoning boundary implicitly. If reasoning was requested and no
   fallback supports it, we fail rather than quietly returning a non-reasoned answer.
5. Each fallback attempt consumes budget. A chain cannot multiply spend beyond the run's
   remaining allowance.
6. Mid-stream fallback restarts the turn from the user message, archiving the partial. Tokens
   already emitted are still billed, which is accounted for honestly rather than hidden.

## 6. Token counting and context budgeting

Token counting is used before the call, for context packing and budget preflight, and it
cannot be exact for every provider. Strategy by provider capability:

- **Exact, server-side**: Anthropic's token-counting endpoint, used for Claude models when the
  payload is large enough to matter.
- **Exact, local**: `tiktoken` for OpenAI models.
- **Estimated**: `len(text) / 3.6` characters-per-token for everything else, with a 15 % safety
  margin. Deliberately conservative, because overflowing the context is a hard failure while
  under-packing is only slightly wasteful.

Context assembly order, with a budget per section (percentages of `context_window`):

```
system prompt + tool schemas        (hard requirement, measured, never trimmed)
memory block                        (≤ 15 %, see memory-system.md)
pinned artifacts and attachments    (≤ 25 %, summarized if over)
conversation history                (fills remainder, newest-first, whole turns only)
reserved for output                 (max_output_tokens, including reasoning budget)
```

Dropping history drops **whole turns**, never half a turn, and never a tool result without its
tool call — an orphaned `tool_result` is a hard 400 from every provider and one of the most
common bugs in home-grown agent loops. A dropped-history marker part is inserted so the user
can see that truncation happened rather than wondering why the model forgot.

## 7. Testing

| Test | Scope |
| --- | --- |
| Stream-event normalization | Recorded provider streams (fixtures, secrets scrubbed) replayed through each provider implementation, asserting an identical `StreamEvent` sequence |
| Error mapping | A table of provider error payloads to `ProviderErrorKind`, one case per row in §4 |
| Reasoning translation | Each `reasoning_control` dialect across all four levels, asserting the exact outbound request body |
| Context packing | Property test: for random histories and window sizes, the packed context never exceeds budget and never orphans a tool result |
| Registry seeding | `models.yaml` upsert is idempotent; a second run produces no changes |
| Fallback | Simulated `rate_limited` triggers fallback; `content_filtered` does not |
| Key validation | Mocked provider responses mapped to `KeyStatus` |

Explicitly **not** tested: live calls to real providers in CI. They are slow, flaky, cost money,
and test the provider rather than our code. A nightly smoke job calls one cheap model per
provider with a dedicated key and alerts on a change in wire behaviour — that is where
real-provider testing belongs.
