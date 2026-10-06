# ADR-0009: LiteLLM as the default provider, with native implementations where fidelity matters

**Status:** Accepted
**Date:** 2026-10-06

## Context

Users must be able to pick any model, including models released after our last deploy, across
Anthropic, OpenAI, Google, open-source, and local endpoints. Each provider differs in streaming
format, tool-call encoding, and — most awkwardly — how reasoning is requested and returned.

A normalizing library solves most of this. It also, inevitably, lags the frontier: extended
thinking with interleaved tool use, the OpenAI Responses API, and provider-specific prompt-cache
controls are exactly the features that differentiate a good agent product, and exactly what a
normalizing layer smooths over or ships late.

## Decision

Our own `LLMProvider` protocol is the contract — four methods, and a closed `StreamEvent` union.

`LiteLLMProvider` is the default implementation and handles the long tail of providers.
`AnthropicProvider` and `OpenAIProvider` are native implementations used for those two
providers. Selection is by `model_providers.implementation`, a **database value**.

## Consequences

**Easier:** a new provider is usually zero code — LiteLLM already supports it, so it is a
`models.yaml` entry. Frontier features on the two providers that matter most are available
immediately. Switching a provider between native and LiteLLM is a database update, so when
LiteLLM ships support for something we hand-rolled, we drop back with no code change in the
agent runtime.

**Harder:** two implementations to keep behaviourally identical for Anthropic and OpenAI. This
is addressed by testing both against the same recorded-stream fixtures and asserting an
identical `StreamEvent` sequence — if they diverge, a test fails.

**Live with:** reasoning blocks that providers return redacted or encrypted must be stored and
replayed byte-identical, or the provider rejects the following turn. The abstraction therefore
has an opaque passthrough field, which is slightly unsatisfying but unavoidable.

## Alternatives considered

**LangChain chat models.** Rejected: it couples the entire runtime to LangChain's abstraction and
release cadence when we only want LangGraph. The history of churn in that interface makes it a
poor foundation for a provider layer.

**OpenRouter for everything.** Rejected outright: it routes the user's prompts and their BYO
keys through a third party, which directly contradicts the privacy position that makes BYOK the
product. Users may still *choose* OpenRouter as an OpenAI-compatible endpoint.

**Hand-rolled adapters for every provider.** Rejected: unbounded maintenance for the long tail,
and the long tail is where "any model" gets its value.

**Running the LiteLLM proxy server.** Rejected: another service to operate, another hop, and it
would hold decrypted user keys outside our application boundary.
