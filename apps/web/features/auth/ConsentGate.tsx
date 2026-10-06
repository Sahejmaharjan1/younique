"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type RequiredDoc = { id: string; kind: string; version: number; summary_of_changes: string; url: string };

export function ConsentGate() {
  const [required, setRequired] = useState<RequiredDoc[]>([]);

  useEffect(() => {
    void api<{ consent_required: RequiredDoc[] }>("/api/v1/me").then((body) => {
      setRequired(body.consent_required);
    });
  }, []);

  async function accept(id: string) {
    await api("/api/v1/me/consents", { method: "POST", body: JSON.stringify({ document_id: id }) });
    setRequired((current) => current.filter((doc) => doc.id !== id));
  }

  if (required.length === 0) return <p>You are up to date.</p>;
  return (
    <div>
      {required.map((doc) => (
        <section className="card" key={doc.id}>
          <h2>
            {doc.kind} v{doc.version}
          </h2>
          <p>{doc.summary_of_changes}</p>
          <a href={doc.url}>Read</a>
          <button type="button" onClick={() => void accept(doc.id)}>
            Accept
          </button>
        </section>
      ))}
    </div>
  );
}
