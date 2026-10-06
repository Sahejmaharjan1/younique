from __future__ import annotations

from younique.llm.types import PriceSnapshot


def cost_micro_usd(
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    price: PriceSnapshot,
) -> int:
    uncached = input_tokens - cached_input_tokens
    if uncached < 0:
        uncached = 0
    total = (
        uncached * price.input_micro_usd_per_mtok
        + cached_input_tokens * price.cached_input_micro_usd_per_mtok
        + output_tokens * price.output_micro_usd_per_mtok
        + reasoning_tokens * price.reasoning_micro_usd_per_mtok
    )
    return total // 1_000_000
