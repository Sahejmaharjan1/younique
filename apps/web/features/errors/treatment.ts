export type ErrorTreatment =
  | "inline-retry"
  | "switch-model"
  | "settings"
  | "reconnect"
  | "consent"
  | "reauth"
  | "inline-card"
  | "toast"
  | "error-page";

const TREATMENTS: Record<string, ErrorTreatment> = {
  provider_rate_limited: "inline-retry",
  provider_timeout: "inline-retry",
  provider_unavailable: "inline-retry",
  provider_model_deprecated: "switch-model",
  provider_context_length_exceeded: "switch-model",
  provider_invalid_key: "settings",
  budget_exceeded: "settings",
  quota_exceeded: "settings",
  connection_needs_reauth: "reconnect",
  connection_revoked: "reconnect",
  consent_required: "consent",
  reauth_required: "reauth",
  tool_blocked_by_policy: "inline-card",
  tool_blocked_by_taint: "inline-card",
  artifact_not_clean: "inline-card",
  artifact_scan_failed: "inline-card",
  unsupported_file_type: "inline-card",
  internal_error: "error-page",
};

export function treatmentFor(code: string | undefined): ErrorTreatment {
  if (!code) return "toast";
  return TREATMENTS[code] ?? "toast";
}

export function treatmentCopy(code: string, detail?: string): string {
  const treatment = treatmentFor(code);
  if (treatment === "inline-retry")
    return detail || "The provider is busy. Retry the message.";
  if (treatment === "switch-model")
    return detail || "This model cannot finish the request. Switch models.";
  if (treatment === "settings")
    return detail || "Update the setting that blocks this request.";
  if (treatment === "reconnect")
    return detail || "Reconnect the service and try again.";
  if (treatment === "consent")
    return detail || "Accept the current terms to continue.";
  if (treatment === "reauth") return detail || "Sign in again to continue.";
  if (treatment === "inline-card") return detail || "This action is blocked.";
  if (treatment === "error-page") return detail || "Something went wrong.";
  return detail || code;
}
