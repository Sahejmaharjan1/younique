"use client";

import { treatmentCopy, treatmentFor } from "@/features/errors/treatment";

export function ErrorNotice({
  code,
  detail,
  requestId,
}: {
  code: string;
  detail?: string;
  requestId?: string;
}) {
  const treatment = treatmentFor(code);
  return (
    <article className={`card error-${treatment}`} data-error-code={code}>
      <p>{treatmentCopy(code, detail)}</p>
      {treatment === "settings" ? (
        <a href="/settings/keys">Open settings</a>
      ) : null}
      {treatment === "reauth" ? <a href="/login">Sign in again</a> : null}
      {treatment === "consent" ? <a href="/consent">Review terms</a> : null}
      {treatment === "reconnect" ? <a href="/connections">Reconnect</a> : null}
      {treatment === "switch-model" ? (
        <a href="/chat/new">Switch model</a>
      ) : null}
      {requestId ? (
        <p>
          Request <code>{requestId}</code>
        </p>
      ) : null}
    </article>
  );
}
