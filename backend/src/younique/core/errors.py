from __future__ import annotations

from typing import Any


class ProblemDetail(Exception):
    def __init__(
        self,
        *,
        status: int,
        code: str,
        title: str,
        detail: str | None = None,
        retryable: bool = False,
        remediation: dict[str, str] | None = None,
        errors: list[dict[str, str]] | None = None,
        resource: dict[str, str] | None = None,
        retry_after_ms: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.retryable = retryable
        self.remediation = remediation
        self.errors = errors
        self.resource = resource
        self.retry_after_ms = retry_after_ms
        self.extra = extra or {}
        super().__init__(detail or title)

    def to_dict(self, request_id: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": f"https://younique.dev/errors/{self.code}",
            "title": self.title,
            "status": self.status,
            "code": self.code,
            "retryable": self.retryable,
            "request_id": request_id,
        }
        if self.detail is not None:
            body["detail"] = self.detail
        if self.remediation is not None:
            body["remediation"] = self.remediation
        if self.errors is not None:
            body["errors"] = self.errors
        if self.resource is not None:
            body["resource"] = self.resource
        if self.retry_after_ms is not None:
            body["retry_after_ms"] = self.retry_after_ms
        body.update(self.extra)
        return body


def problem(
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    **kwargs: Any,
) -> ProblemDetail:
    return ProblemDetail(status=status, code=code, title=title, detail=detail, **kwargs)


def unauthenticated(detail: str = "Authentication is required.") -> ProblemDetail:
    return problem(401, "unauthenticated", "Unauthenticated", detail)


def session_expired(detail: str = "The session is expired.") -> ProblemDetail:
    return problem(401, "session_expired", "Session expired", detail)


def session_revoked(detail: str = "The session was revoked.") -> ProblemDetail:
    return problem(401, "session_revoked", "Session revoked", detail)


def csrf_failed() -> ProblemDetail:
    return problem(403, "csrf_failed", "CSRF check failed", "The CSRF token did not match.")


def consent_required(required: list[dict[str, Any]]) -> ProblemDetail:
    return problem(
        409,
        "consent_required",
        "Consent required",
        "Updated terms require your acceptance.",
        extra={"required": required},
    )


def permission_denied(detail: str = "You cannot perform that action.") -> ProblemDetail:
    return problem(403, "permission_denied", "Permission denied", detail)


def not_found() -> ProblemDetail:
    return problem(404, "not_found", "Not found", "The resource does not exist.")


def archived() -> ProblemDetail:
    return problem(410, "archived", "Archived", "The resource is archived.")


def validation_failed(errors: list[dict[str, str]]) -> ProblemDetail:
    return problem(
        422,
        "validation_failed",
        "Validation failed",
        "The request body is invalid.",
        errors=errors,
    )


def conflict(code: str, detail: str) -> ProblemDetail:
    return problem(409, code, "Conflict", detail, retryable=code == "idempotency_in_flight")


def rate_limited(retry_after_ms: int) -> ProblemDetail:
    return problem(
        429,
        "rate_limited",
        "Rate limited",
        "Too many requests.",
        retryable=True,
        retry_after_ms=retry_after_ms,
    )


def reauth_required() -> ProblemDetail:
    return problem(
        403,
        "reauth_required",
        "Re-authentication required",
        "Confirm your identity to continue.",
        remediation={
            "message": "Sign in again to continue.",
            "action": "step_up",
            "href": "/login",
        },
    )


def artifact_not_clean(status: str) -> ProblemDetail:
    return problem(
        409,
        "artifact_not_clean",
        "Artifact is not clean",
        f"Download is blocked while status is {status}.",
    )
