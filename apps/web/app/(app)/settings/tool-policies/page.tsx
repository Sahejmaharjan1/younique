"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function ToolPoliciesPage() {
  const [saved, setSaved] = useState("");
  return (
    <main>
      <h1>Tool policy</h1>
      <button
        type="button"
        onClick={() => {
          void api("/api/v1/tool-policies", {
            method: "PUT",
            body: JSON.stringify({
              tool_key: "gmail.send_email",
              mode: "never",
              allow_when_tainted: false,
            }),
          }).then(() => setSaved("gmail.send_email is never"));
        }}
      >
        Never send mail
      </button>
      {saved ? <p>{saved}</p> : null}
    </main>
  );
}
