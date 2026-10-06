"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { readSse } from "@/lib/sse";

type Part = { text: string; live: boolean };

export function ChatView({ chatId }: { chatId: string }) {
  const [parts, setParts] = useState<Part[]>([]);
  const [draft, setDraft] = useState("");
  const liveRef = useRef<HTMLDivElement>(null);

  async function send() {
    const response = await api<Response>(`/api/v1/chats/${chatId}/messages`, {
      method: "POST",
      headers: { accept: "text/event-stream" },
      body: JSON.stringify({ text: draft }),
    });
    setDraft("");
    for await (const event of readSse(response)) {
      if (event.event === "part.delta") {
        const body = JSON.parse(event.data) as { text?: string };
        setParts((current) => [...current, { text: body.text ?? "", live: true }]);
      }
      if (event.event === "approval.required") {
        const body = JSON.parse(event.data) as { summary?: { headline?: string; flagged_args?: string[] } };
        const flagged = body.summary?.flagged_args?.join(", ") ?? "";
        setParts((current) => [
          ...current,
          { text: `${body.summary?.headline ?? "Approval required"}${flagged ? ` (from untrusted input: ${flagged})` : ""}`, live: false },
        ]);
      }
    }
  }

  return (
    <section>
      <div aria-live="polite" ref={liveRef}>
        {parts.map((part, index) => (
          <p key={`${index}-${part.text.slice(0, 12)}`}>{part.text}</p>
        ))}
      </div>
      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <textarea
          aria-label="Message"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <button type="submit">Send</button>
      </form>
    </section>
  );
}
