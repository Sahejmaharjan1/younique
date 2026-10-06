"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function NewChatPage() {
  const [title, setTitle] = useState("New chat");
  return (
    <main>
      <h1>New chat</h1>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void api<{ id: string }>("/api/v1/chats", {
            method: "POST",
            body: JSON.stringify({ title }),
          }).then((chat) => {
            window.location.assign(`/chat/${chat.id}`);
          });
        }}
      >
        <label>
          Title
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <button type="submit">Start</button>
      </form>
    </main>
  );
}
