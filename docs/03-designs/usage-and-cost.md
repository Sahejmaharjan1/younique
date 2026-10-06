# Usage Metering and Cost Control

Users bring their own API keys, so this system is not billing them — it is protecting them. The
design goal is that a user never discovers a surprise on their Anthropic invoice that Younique
could have warned them about.

That reframing changes the priorities: **accuracy of attribution** and **pre-emptive limits**
matter more than invoice-grade precision.

## 1. The ledger

`app.usage_events` is append-only, monthly-partitioned, and never updated. One row per billable
provider call.

```sql
INSERT INTO app.usage_events (
  id, workspace_id, occurred_at,
  run_id, run_step_id, chat_id, agent_id, pipeline_id,   -- attribution, denormalized
  model_id, provider_key_id, kind,                       -- 'completion'|'embedding'|'rerank'
  input_tokens, cached_input_tokens, output_tokens, reasoning_tokens,
  cost_micro_usd, price_snapshot, request_id, latency_ms, was_fallback
) VALUES (...)
ON CONFLICT (request_id) DO NOTHING;
```

Four properties that are each load-bearing:

**Attribution is denormalized.** `chat_id`, `agent_id`, and `pipeline_id` are copied onto the
row rather than being joined through `runs`. The dashboards group by these, and a join through
a partitioned table for every aggregation is exactly the query that gets slow first. Storage is
cheap; a slow usage page is not.

**`cost_micro_usd` is computed at write time** from the `model_prices` row effective at
`occurred_at`, and the entire price row is copied into `price_snapshot`. Historical cost is
immutable. Recomputing from current prices — the obvious shortcut — silently rewrites financial
history and makes last month's figure irreproducible, which is the one thing a cost dashboard
must never do.

**`ON CONFLICT (request_id) DO NOTHING` is the idempotency barrier.** A Cloud Tasks retry of a
step whose model call already succeeded would otherwise double-count. `request_id` is the
provider's own request ID where available (`x-request-id` from Anthropic and OpenAI), otherwise
a deterministic hash of `(run_step_id, attempt, model_id)`.

**Cached-input and reasoning tokens are separate columns.** They are priced differently —
cached input is often a tenth of the price, reasoning output is sometimes the dominant cost —
and collapsing them into `input`/`output` makes the arithmetic wrong and the user's surprise
unexplainable.

### Recording on failure

Usage is recorded from the provider's `Usage` stream event, or reconstructed from counted
tokens if the stream was interrupted. A partial stream **still cost money** and is still
recorded. A turn that failed after generating 4000 tokens appears in the ledger, because the
alternative is a dashboard that undercounts and a user who does not trust it.

## 2. Cost computation

```python
def compute_cost(u: TokenUsage, p: ModelPrice) -> int:
    return (
        (u.input_tokens - u.cached_input_tokens) * p.input_micro_usd_per_mtok
      + u.cached_input_tokens                   * p.cached_input_micro_usd_per_mtok
      + u.output_tokens                         * p.output_micro_usd_per_mtok
      + u.reasoning_tokens                      * (p.reasoning_micro_usd_per_mtok
                                                   or p.output_micro_usd_per_mtok)
    ) // 1_000_000
```

Integer arithmetic throughout, in micro-USD. Floats for money produce drift that shows up as a
dashboard total disagreeing with the sum of its rows, which looks like a bug in the product
even when the error is a rounding artifact.

`reasoning_micro_usd_per_mtok` falls back to the output price because most providers bill
thinking tokens as output. Where a provider bills them differently, the registry carries the
distinct price.

Known limits, documented in the UI rather than hidden: provider-side prompt caching discounts
are reflected only when the provider reports cached tokens; batch-API discounts, enterprise
committed-use rates, and free-tier allowances are not modelled. The dashboard says
"estimated based on public list prices" with a link to the explanation. Claiming precision we
do not have would be worse than being clear about the approximation.

## 3. Rollups

Raw events power reconciliation; aggregates power dashboards.

```sql
CREATE TABLE analytics.usage_daily (
  workspace_id uuid NOT NULL,
  day          date NOT NULL,
  model_id     uuid,
  user_id      uuid,
  agent_id     uuid,
  pipeline_id  uuid,
  kind         text NOT NULL,
  input_tokens bigint NOT NULL DEFAULT 0,
  cached_input_tokens bigint NOT NULL DEFAULT 0,
  output_tokens bigint NOT NULL DEFAULT 0,
  reasoning_tokens bigint NOT NULL DEFAULT 0,
  cost_micro_usd bigint NOT NULL DEFAULT 0,
  call_count   int NOT NULL DEFAULT 0,
  error_count  int NOT NULL DEFAULT 0,
  PRIMARY KEY (workspace_id, day, model_id, user_id, agent_id, pipeline_id, kind)
);
```

A nightly `nightly-rollup` task recomputes the trailing 3 days (idempotent `INSERT ... ON
CONFLICT DO UPDATE`) to absorb late-arriving events from long runs. `GET /v1/usage` reads
`usage_daily` for anything older than today and sums raw events for today, so the current day
is live while history is fast.

A regular table rather than a materialized view: `REFRESH MATERIALIZED VIEW CONCURRENTLY`
rebuilds everything, which becomes minutes of work for a small daily delta, and the 3-day
recompute window is the behaviour we actually want.

**A reconciliation test asserts that `SUM(usage_events.cost)` for a period equals
`SUM(usage_daily.cost)` for the same period.** When a cost dashboard disagrees with itself,
users stop believing all of it.

## 4. Budgets and enforcement

`app.budgets` is scoped to a workspace, user, agent, or pipeline, over a day or a month, with
`action` of `warn` or `block` and a `warn_at_fraction` (default 0.8).

Enforcement at three points, each catching a different failure:

| Point | Check | Behaviour on breach |
| --- | --- | --- |
| **Run start (preflight)** | Current period spend plus the estimated run cost against every applicable budget | `block`: refuse with `402 budget_exceeded`, including current spend, limit, and the reset time. `warn`: proceed and notify. |
| **Before each model call** | Remaining run budget against the estimated call cost | Halt the run with `budget_exceeded`, **persisting partial results**. A halted run is far better than a halved invoice. |
| **After each call (post-hoc)** | Actual against limit | Crossing `warn_at_fraction` emits one notification per period, deduplicated. Crossing a `block` limit pauses dependent schedules. |

Estimation before the fact is necessarily approximate: input tokens are countable, output
tokens are not. We estimate output at `min(max_output_tokens, 2000)` for a chat turn and use
the agent's observed p90 for a background run, which gets accurate after a few runs. The
estimate is deliberately conservative — overestimating causes an unnecessary warning;
underestimating causes an overrun, and only one of those is recoverable.

**`block` pauses, it does not fail silently.** A blocked schedule moves to `paused` with
`pause_reason = 'budget_exceeded'`, the user is notified, and resuming is one click after they
raise the limit. Leaving a schedule to fail every morning until someone notices is the
behaviour that makes people abandon automation products.

### Non-cost limits

Budgets cover money. Three other limits cover abuse and runaway loops, enforced at claim time
and in the graph:

| Limit | Default | Where |
| --- | --- | --- |
| Runs per minute per workspace | 60 | API rate limiter |
| Concurrent runs per workspace | 10 (plan-dependent) | Claim-time count |
| Tool calls per run | 50 | `AgentState.tool_call_count` |
| Steps per run | 25 | `AgentState.step_count` |
| Platform-paid embedding tokens per month | 1 M per workspace | Checked before the embedding call |

## 5. Dashboards

One usage page, four views, all served by `GET /v1/usage` with a different `group_by`.

| View | Visual | Answers |
| --- | --- | --- |
| Overview | Stacked area of daily cost by model, with budget lines overlaid | "What am I spending and am I near a limit?" |
| By model | Bar chart plus table with cost, calls, tokens, p50/p95 latency, error rate | "Is the expensive model worth it?" |
| By agent and pipeline | Table with cost per run, run count, success rate, trend sparkline | "Which automation is eating my budget?" |
| By chat | Sortable list, most expensive first | "Which conversation cost that much?" |

Plus three smaller surfaces that matter more than the dashboard in practice, because they
appear where the decision is made:

- **Per-message cost** in the chat, shown on hover: tokens in, out, reasoning, and cost. This
  is what teaches a user that reasoning mode is expensive, at the moment they could turn it off.
- **Per-run cost** on every run detail page, broken down by step, so an expensive step is
  immediately visible.
- **A cost estimate before publishing a schedule**: "roughly $0.42 per run, about $1.68 per
  month at weekly." Preventing a bad schedule is worth more than reporting on one.

Charts use Recharts, every chart has an accessible table equivalent behind a toggle, and all
currency is formatted to 4 decimal places below $1 and 2 above — because `$0.00` for a real
cost makes a dashboard look broken.

## 6. Multi-currency and display

Provider prices are USD. Users may not think in USD. `users.display_currency` converts at a
daily-cached rate from a free FX source, with the USD figure always shown alongside and a
"converted at X on date Y" note. Converted figures are never stored — only displayed — so the
ledger stays single-currency and auditable.

## 7. Testing

| Test | Proves |
| --- | --- |
| Cost arithmetic | A table of token mixes and prices against hand-computed micro-USD, including cached input and reasoning |
| Price snapshot immutability | Change a price, then re-read an old event, and assert the cost is unchanged |
| Idempotency | Inserting the same `request_id` twice yields one row and one cost |
| Interrupted stream | A partial turn still writes a usage event with the tokens generated |
| Rollup reconciliation | Raw sum equals daily sum over a seeded month, including a late-arriving event inside the 3-day window |
| Budget block at preflight | A run that would exceed a `block` budget is refused with the limit and reset time in the body |
| Mid-run halt | A run crossing its budget mid-way halts and persists partial results |
| Warning dedupe | Crossing 80 % twice in one period sends exactly one notification |
| Schedule pause on block | A blocked budget pauses the schedule with a reason, and resume works after the limit is raised |
| Attribution | A sub-agent's cost rolls up to the parent run and to the owning agent, counted exactly once |

**Not tested:** exact agreement with a provider's invoice (we cannot see their billing system,
and discounts we do not model make exact agreement impossible — this is documented as an
estimate rather than tested as a fact), and FX rate accuracy.
