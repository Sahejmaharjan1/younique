"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function ConnectionsPage() {
  const [host, setHost] = useState("smtp.example");
  const [username, setUsername] = useState("me@example.com");
  const [password, setPassword] = useState("app-password");
  const [connected, setConnected] = useState("");

  return (
    <main>
      <h1>Connections</h1>
      <p>
        SMTP sends mail without Google verification. Gmail needs your own OAuth
        client until CASA completes.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void api<{ id: string }>("/api/v1/connections/smtp", {
            method: "POST",
            body: JSON.stringify({ host, port: 587, username, password }),
          }).then((row) => setConnected(row.id));
        }}
      >
        <label>
          Host
          <input
            value={host}
            onChange={(event) => setHost(event.target.value)}
          />
        </label>
        <label>
          Username
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button type="submit">Connect SMTP</button>
      </form>
      {connected ? <p>SMTP connected {connected}</p> : null}
    </main>
  );
}
