import random

from younique.llm.errors import normalize_provider_error, retry_action
from younique.llm.packing import pack_messages
from younique.llm.reasoning import translate_reasoning
from younique.llm.types import PriceSnapshot
from younique.usage.cost import cost_micro_usd


def test_cost_arithmetic_uses_snapshot() -> None:
    price = PriceSnapshot(
        input_micro_usd_per_mtok=3_000_000,
        output_micro_usd_per_mtok=15_000_000,
        cached_input_micro_usd_per_mtok=300_000,
        reasoning_micro_usd_per_mtok=15_000_000,
    )
    cost = cost_micro_usd(
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=1_000,
        reasoning_tokens=2_000,
        price=price,
    )
    assert cost == 750_000 * 3 + 250_000 * 300_000 // 1_000_000 + 1_000 * 15 + 2_000 * 15
    changed = price.model_copy(update={"input_micro_usd_per_mtok": 1})
    assert cost_micro_usd(
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=1_000,
        reasoning_tokens=2_000,
        price=price,
    ) != cost_micro_usd(
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=1_000,
        reasoning_tokens=2_000,
        price=changed,
    )


def test_retry_policy() -> None:
    invalid = normalize_provider_error(401, "invalid")
    assert retry_action(invalid, 0) == "fail"
    limited = normalize_provider_error(429, "slow", "2")
    assert limited.retry_after_ms == 2000
    assert retry_action(limited, 3) == "fail"
    assert retry_action(normalize_provider_error(503, "down"), 2) == "fallback"


def test_reasoning_dialects() -> None:
    assert translate_reasoning("boolean", True)["reasoning"]["enabled"] is True
    assert translate_reasoning("effort", True, "high")["reasoning_effort"] == "high"
    assert "budget_tokens" in translate_reasoning("budget_tokens", True)["thinking"]
    assert translate_reasoning("none", True) == {}


def test_packing_never_orphans_tool_results() -> None:
    rng = random.Random(7)
    for _ in range(30):
        messages = [{"role": "system", "content": "rules"}]
        for index in range(rng.randint(1, 8)):
            call = f"call-{index}"
            messages.append(
                {"role": "assistant", "content": "x" * rng.randint(10, 80), "tool_call_id": call}
            )
            messages.append(
                {"role": "tool", "content": "y" * rng.randint(10, 80), "tool_call_id": call}
            )
        packed = pack_messages(messages, budget_tokens=40)
        calls = {
            m["tool_call_id"] for m in packed if m["role"] == "assistant" and m.get("tool_call_id")
        }
        results = {
            m["tool_call_id"] for m in packed if m["role"] == "tool" and m.get("tool_call_id")
        }
        assert calls == results
        assert sum(len(str(m.get("content"))) // 4 for m in packed) <= 80
