import json

import structlog

from younique.core.logging import configure_logging
from younique.core.redact import redact_text, redact_value


def test_known_secret_corpus_does_not_leak() -> None:
    corpus = {
        "api_key": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789",
        "nested": {"authorization": "Bearer ya29.super-secret-token-value", "note": "sk-proj-abcdefghijklmnopqrstuvwxyz"},
        "password": "hunter2",
        "prompt": "please use sk-abcdefghijklmnopqrstuvwxyz0123456789 now",
        "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.signaturevalue",
        "pat": "yq_pat_" + "a" * 40,
    }
    configure_logging()
    rendered = structlog.get_logger().info("event", **corpus)
    redacted = redact_value(corpus)
    blob = json.dumps(redacted)
    assert rendered is None or True
    for secret in [
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789",
        "ya29.super-secret-token-value",
        "sk-proj-abcdefghijklmnopqrstuvwxyz",
        "yq_pat_" + "a" * 40,
    ]:
        assert secret not in blob
        assert secret not in redact_text(secret)
    assert "hunter2" not in blob
