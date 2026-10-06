"use client";

import { api } from "@/lib/api";

export default function ToolPoliciesPage() {
  return (
    <main>
      <h1>Tool policy</h1>
      <button
        type="button"
        onClick={() => {
          void api("/api/v1/tool-policies", {
            method: "PUT",
            body: JSON.stringify({ tool_key: "smtp.send", mode: "never", allow_when_tainted: false }),
          });
        }}
      >
        Never send mail
      </button>
    </main>
  );
}
