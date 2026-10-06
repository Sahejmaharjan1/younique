"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Share = {
  title: string | null;
  messages: { role: string; parts: { content: string | null }[] }[];
  excludes: string[];
};

export function ShareView({ token }: { token: string }) {
  const [body, setBody] = useState<Share | null>(null);
  const [blocked, setBlocked] = useState("");

  useEffect(() => {
    void fetch(`/api/v1/public/${token}`).then(async (response) => {
      if (!response.ok) {
        setBlocked("This link is not active.");
        return;
      }
      setBody((await response.json()) as Share);
    });
  }, [token]);

  async function probe() {
    try {
      await api("/api/v1/connections");
    } catch {
      setBlocked("connections are not available from a share link");
    }
  }

  if (blocked && !body) return <p>{blocked}</p>;
  return (
    <section>
      <h2>{body?.title || "Shared chat"}</h2>
      {body?.messages.map((message, index) => (
        <p key={index}>{message.parts.map((part) => part.content).join(" ")}</p>
      ))}
      <p>Excludes {body?.excludes.join(", ")}</p>
      <button type="button" onClick={() => void probe()}>
        Try connections
      </button>
      {blocked ? <p>{blocked}</p> : null}
    </section>
  );
}
