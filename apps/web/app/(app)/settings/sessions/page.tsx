"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Row = { id: string; is_current: boolean; revoked_at: string | null };

export default function SessionsPage() {
  const [rows, setRows] = useState<Row[]>([]);
  useEffect(() => {
    void api<{ data: Row[] }>("/api/v1/me/sessions").then((body) =>
      setRows(body.data),
    );
  }, []);
  return (
    <main>
      <h1>Devices</h1>
      {rows.map((row) => (
        <article className="card" key={row.id}>
          <p>{row.is_current ? "This device" : row.id}</p>
          <button
            type="button"
            onClick={() => {
              void api(`/api/v1/me/sessions/${row.id}:revoke`, {
                method: "POST",
              }).then(() => {
                setRows((current) =>
                  current.map((item) =>
                    item.id === row.id ? { ...item, revoked_at: "now" } : item,
                  ),
                );
              });
            }}
          >
            Revoke
          </button>
        </article>
      ))}
    </main>
  );
}
