"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function NewChatPage() {
  const [title, setTitle] = useState("New chat");

  function start() {
    void api<{ id: string }>("/api/v1/chats", {
      method: "POST",
      body: JSON.stringify({ title }),
    }).then((chat) => {
      window.location.assign(`/chat/${chat.id}`);
    });
  }

  return (
    <main>
      <h1>New chat</h1>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void start();
        }}
      >
        <label>
          Title
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <button type="button" onClick={() => void start()}>
          Start
        </button>
      </form>
    </main>
  );
}
