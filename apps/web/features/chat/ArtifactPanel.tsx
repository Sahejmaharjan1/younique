"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Artifact = {
  id: string;
  name: string;
  status: string;
  detected_mime: string | null;
};

export function ArtifactPanel({ chatId }: { chatId: string }) {
  const [rows, setRows] = useState<Artifact[]>([]);
  useEffect(() => {
    void api<{ data: Artifact[] }>(`/api/v1/chats/${chatId}/artifacts`).then(
      (body) => setRows(body.data),
    );
  }, [chatId]);
  return (
    <aside className="artifacts-panel">
      <h2>Files</h2>
      {rows.length === 0 ? <p>No files yet.</p> : null}
      <ul>
        {rows.map((row) => (
          <li key={row.id}>
            {row.name} · {row.status}
            {row.detected_mime === "application/pdf" &&
            row.status === "clean" ? (
              <PdfNote name={row.name} />
            ) : null}
          </li>
        ))}
      </ul>
    </aside>
  );
}

function PdfNote({ name }: { name: string }) {
  const srcDoc = `<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'"><p>${name}</p>`;
  return <iframe sandbox="" title="PDF preview" srcDoc={srcDoc} />;
}
