export const paths = [
  "/healthz",
  "/internal/events/gcs-upload",
  "/internal/tasks/agent-run",
  "/internal/tasks/artifact-scan",
  "/internal/tasks/outbox-drain",
  "/internal/tasks/pipeline-run",
  "/readyz",
  "/v1/approvals",
  "/v1/approvals/{approval_id}:decide",
  "/v1/artifacts",
  "/v1/artifacts/{artifact_id}",
  "/v1/artifacts/{artifact_id}/content",
  "/v1/artifacts/{artifact_id}/download",
  "/v1/artifacts/{artifact_id}/preview",
  "/v1/auth/accounts",
  "/v1/auth/session",
  "/v1/chats",
  "/v1/chats/{chat_id}",
  "/v1/chats/{chat_id}/artifacts",
  "/v1/chats/{chat_id}/messages",
  "/v1/chats/{chat_id}/messages:regenerate",
  "/v1/chats/{chat_id}/share-links",
  "/v1/chats/{chat_id}:restore",
  "/v1/connections",
  "/v1/connections/smtp",
  "/v1/connectors",
  "/v1/dev/mailbox",
  "/v1/me",
  "/v1/me/consents",
  "/v1/me/sessions",
  "/v1/me/sessions/{session_id}:revoke",
  "/v1/models",
  "/v1/provider-keys",
  "/v1/provider-keys/{key_id}:revoke",
  "/v1/provider-keys/{key_id}:rotate",
  "/v1/public/{token}",
  "/v1/runs/{run_id}/events",
  "/v1/runs/{run_id}:cancel",
  "/v1/share-links/{link_id}:revoke",
  "/v1/tool-policies",
  "/v1/usage",
  "/v1/usage/events",
] as const;

export type Problem = {
  type: string;
  title: string;
  status: number;
  code: string;
  retryable: boolean;
  request_id: string;
  detail?: string;
};

export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  return fetch(path, { credentials: "include", ...init });
}
