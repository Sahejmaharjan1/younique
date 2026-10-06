from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProviderFailure:
    code: str
    status: int
    retryable: bool
    retry_after_ms: int | None = None
    detail: str = ""


def normalize_provider_error(
    status: int, body: str, retry_after: str | None = None
) -> ProviderFailure:
    retry_after_ms = None
    if retry_after and retry_after.isdigit():
        retry_after_ms = int(retry_after) * 1000
    if status == 401:
        return ProviderFailure("provider_invalid_key", 400, False, detail=body)
    if status == 402:
        return ProviderFailure("provider_insufficient_quota", 402, False, detail=body)
    if status == 429:
        return ProviderFailure("provider_rate_limited", 429, True, retry_after_ms, body)
    if status == 408 or status == 504:
        return ProviderFailure("provider_timeout", 504, True, detail=body)
    if status >= 500:
        return ProviderFailure("provider_unavailable", 502, True, detail=body)
    if "context" in body.lower() and "length" in body.lower():
        return ProviderFailure("provider_context_length_exceeded", 400, False, detail=body)
    if "content" in body.lower() and "filter" in body.lower():
        return ProviderFailure("provider_content_filtered", 400, False, detail=body)
    if "deprecat" in body.lower():
        return ProviderFailure("provider_model_deprecated", 400, False, detail=body)
    return ProviderFailure("provider_unavailable", 502, False, detail=body)


Action = Literal["retry", "fallback", "fail"]


def retry_action(failure: ProviderFailure, attempt: int) -> Action:
    if failure.code == "provider_invalid_key":
        return "fail"
    if failure.code == "provider_content_filtered":
        return "fail"
    if failure.code == "provider_model_deprecated":
        return "fail"
    if failure.code == "provider_context_length_exceeded":
        return "retry" if attempt == 0 else "fail"
    if failure.code == "provider_rate_limited":
        return "retry" if attempt < 3 else "fail"
    if failure.code in {"provider_timeout", "provider_unavailable"}:
        return "retry" if attempt < 2 else "fallback"
    return "fail"
