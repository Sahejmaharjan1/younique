"use client";

import { useEffect, useState } from "react";
import { ErrorNotice } from "@/features/errors/ErrorNotice";
import { ApiError, api } from "@/lib/api";

type KeyRow = { id: string; last4: string; status: string; provider: string };

export default function KeysPage() {
  const [secret, setSecret] = useState("");
  const [rows, setRows] = useState<KeyRow[]>([]);
  const [error, setError] = useState<string>("");

  async function load() {
    const body = await api<{ data: KeyRow[] }>("/api/v1/provider-keys");
    setRows(body.data);
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <main>
      <h1>Provider keys</h1>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setError("");
          void api<KeyRow>("/api/v1/provider-keys", {
            method: "POST",
            body: JSON.stringify({ provider: "fake", label: "local", secret }),
          })
            .then(() => {
              setSecret("");
              return load();
            })
            .catch((caught: unknown) => {
              setError(
                caught instanceof ApiError
                  ? caught.message
                  : "Could not save the key.",
              );
            });
        }}
      >
        <label>
          Key
          <input
            type="password"
            value={secret}
            onChange={(event) => setSecret(event.target.value)}
          />
        </label>
        <button type="submit">Save</button>
      </form>
      {error ? <ErrorNotice code="validation_failed" detail={error} /> : null}
      {rows.map((row) => (
        <article className="card" key={row.id}>
          <p>
            {row.provider} · last four characters: {row.last4} · {row.status}
          </p>
          <button
            type="button"
            onClick={() => {
              void api(`/api/v1/provider-keys/${row.id}:rotate`, {
                method: "POST",
                body: JSON.stringify({ secret: "valid-key-rotated" }),
              }).then(() => load());
            }}
          >
            Rotate
          </button>
          <button
            type="button"
            onClick={() => {
              void api(`/api/v1/provider-keys/${row.id}:revoke`, {
                method: "POST",
              }).then(() => load());
            }}
          >
            Revoke
          </button>
        </article>
      ))}
    </main>
  );
}
