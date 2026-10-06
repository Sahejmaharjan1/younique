from __future__ import annotations

from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from younique.core.redact import redact_value


class RedactingProcessor(SimpleSpanProcessor):
    def on_end(self, span: Any) -> None:
        attributes = getattr(span, "attributes", None)
        if isinstance(attributes, dict):
            for key in list(attributes):
                attributes[key] = redact_value(attributes[key], key)
        super().on_end(span)


def configure_otel(enabled: bool) -> None:
    if not enabled:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "younique-api"}))
    provider.add_span_processor(RedactingProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        FastAPIInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
    except Exception:
        return
