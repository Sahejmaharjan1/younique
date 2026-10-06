"use client";

import { useState, type FormEvent } from "react";

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const emulator = process.env.NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST;
    const project =
      process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "demo-younique";
    const endpoint = emulator
      ? `http://${emulator}/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=fake-api-key`
      : "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=firebase";
    const signed = await fetch(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, password, returnSecureToken: true }),
    });
    if (!signed.ok) {
      const created = await fetch(
        endpoint.replace("signInWithPassword", "signUp"),
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ email, password, returnSecureToken: true }),
        },
      );
      if (!created.ok) {
        setMessage("Could not sign in with the auth emulator.");
        return;
      }
      const createdBody = (await created.json()) as { idToken: string };
      await exchange(createdBody.idToken);
      return;
    }
    const body = (await signed.json()) as { idToken: string };
    await exchange(body.idToken);
    setMessage(`Signed in to ${project}.`);
  }

  return (
    <form onSubmit={submit} className="card">
      <label>
        Email
        <input
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          type="email"
          required
        />
      </label>
      <label>
        Password
        <input
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          type="password"
          required
        />
      </label>
      <button type="submit">Continue</button>
      <p>{message}</p>
    </form>
  );
}

async function exchange(idToken: string) {
  await fetch("/api/v1/auth/session", {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ id_token: idToken, step_up: true }),
  });
  window.location.assign("/consent");
}
