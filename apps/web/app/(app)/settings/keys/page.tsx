"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function KeysPage() {
  const [secret, setSecret] = useState("");
  const [last4, setLast4] = useState("");
  return (
    <main>
      <h1>Provider keys</h1>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void api<{ last4: string }>("/api/v1/provider-keys", {
            method: "POST",
            body: JSON.stringify({ provider: "fake", label: "local", secret }),
          }).then((row) => {
            setLast4(row.last4);
            setSecret("");
          });
        }}
      >
        <label>
          Key
          <input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} />
        </label>
        <button type="submit">Save</button>
      </form>
      {last4 ? <p>Stored. Last four characters: {last4}</p> : null}
    </main>
  );
}
