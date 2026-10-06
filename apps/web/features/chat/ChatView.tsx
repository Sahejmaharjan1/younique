"use client";

import { useEffect, useRef, useState } from "react";
import { ArtifactPanel } from "@/features/chat/ArtifactPanel";
import { RichText } from "@/features/chat/RichText";
import { ErrorNotice } from "@/features/errors/ErrorNotice";
import { ApiError, api } from "@/lib/api";
import { readSse, resume } from "@/lib/sse";

type Part = { kind: string; text: string };
type StoredMessage = {
  id: string;
  role: string;
  status: string;
  archived: boolean;
  error_code: string | null;
  parts: { kind: string; content: string | null }[];
};

export function ChatView({ chatId }: { chatId: string }) {
  const [parts, setParts] = useState<Part[]>([]);
  const [history, setHistory] = useState<StoredMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [runId, setRunId] = useState("");
  const [approval, setApproval] = useState<{
    id: string;
    headline: string;
    flagged: string;
  } | null>(null);
  const [error, setError] = useState<{
    code: string;
    detail?: string;
    requestId?: string;
  } | null>(null);
  const [reasoningMode, setReasoningMode] = useState("inherit");
  const [shareToken, setShareToken] = useState("");
  const [shareId, setShareId] = useState("");
  const lastId = useRef("0");
  const liveRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void refresh();
    const saved = sessionStorage.getItem(`run:${chatId}`);
    const seq = sessionStorage.getItem(`run:${chatId}:seq`) || "0";
    if (saved) {
      setRunId(saved);
      void replay(saved, seq);
    }
  }, [chatId]);

  async function refresh() {
    const body = await api<{ data: StoredMessage[] }>(
      `/api/v1/chats/${chatId}/messages`,
    );
    setHistory(body.data);
  }

  async function consume(response: Response) {
    setStreaming(true);
    await new Promise((resolve) =>
      requestAnimationFrame(() => resolve(undefined)),
    );
    try {
      for await (const event of readSse(response)) {
        lastId.current = event.id || lastId.current;
        sessionStorage.setItem(`run:${chatId}:seq`, lastId.current);
        const body = event.data
          ? (JSON.parse(event.data) as Record<string, unknown>)
          : {};
        if (event.event === "run.started" && typeof body.run_id === "string") {
          setRunId(body.run_id);
          sessionStorage.setItem(`run:${chatId}`, body.run_id);
        }
        if (event.event === "part.delta") {
          setParts((current) => [
            ...current,
            {
              kind: String(body.kind || "text"),
              text: String(body.text || ""),
            },
          ]);
        }
        if (event.event === "approval.required") {
          const summary = (body.summary || {}) as {
            headline?: string;
            flagged_args?: string[];
          };
          setApproval({
            id: String(body.approval_id || ""),
            headline: summary.headline || "Approval required",
            flagged: (summary.flagged_args || []).join(", "),
          });
        }
        if (event.event === "error") {
          setError({
            code: String(body.code || "internal_error"),
            detail: typeof body.detail === "string" ? body.detail : undefined,
          });
        }
        if (event.event === "run.completed") setStreaming(false);
      }
    } catch (caught) {
      if (runId) await replay(runId, lastId.current);
      else if (caught instanceof ApiError)
        setError({
          code: caught.code,
          detail: caught.message,
          requestId: caught.requestId,
        });
    } finally {
      setStreaming(false);
      await refresh();
    }
  }

  async function replay(id: string, seq: string) {
    const response = await resume(id, seq);
    if (response.ok) await consume(response);
  }

  async function send() {
    setError(null);
    setApproval(null);
    const response = await api<Response>(`/api/v1/chats/${chatId}/messages`, {
      method: "POST",
      headers: { accept: "text/event-stream" },
      body: JSON.stringify({ text: draft }),
    });
    setDraft("");
    await consume(response);
  }

  async function stop() {
    if (!runId) return;
    await api(`/api/v1/runs/${runId}:cancel`, { method: "POST" });
    setStreaming(false);
    await refresh();
  }

  async function regenerate(messageId: string) {
    const response = await api<Response>(
      `/api/v1/chats/${chatId}/messages:regenerate`,
      {
        method: "POST",
        headers: { accept: "text/event-stream" },
        body: JSON.stringify({ message_id: messageId }),
      },
    );
    await consume(response);
  }

  async function decide(decision: "approve" | "reject") {
    if (!approval) return;
    await api(`/api/v1/approvals/${approval.id}:decide`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    });
    setApproval(null);
    if (runId) await replay(runId, lastId.current);
    await refresh();
  }

  async function toggleReasoning() {
    const next = reasoningMode === "off" ? "on" : "off";
    const saved = await api<{ reasoning_mode: string }>(
      `/api/v1/chats/${chatId}`,
      {
        method: "PATCH",
        body: JSON.stringify({ reasoning_mode: next }),
      },
    );
    setReasoningMode(saved.reasoning_mode);
  }

  const reasoning = parts
    .filter((part) => part.kind === "reasoning")
    .map((part) => part.text)
    .join("");
  const text = parts
    .filter((part) => part.kind === "text")
    .map((part) => part.text)
    .join("");
  const lastAssistant = [...history]
    .reverse()
    .find((message) => message.role === "assistant" && !message.archived);

  return (
    <section className="chat-layout">
      <div>
        <header className="chat-header">
          <button type="button" onClick={() => void toggleReasoning()}>
            Reasoning {reasoningMode === "off" ? "off" : "on"}
          </button>
          <button
            type="button"
            onClick={() => {
              void api<{ id: string; token: string }>(
                `/api/v1/chats/${chatId}/share-links`,
                {
                  method: "POST",
                  body: JSON.stringify({ include_reasoning: false }),
                },
              ).then((link) => {
                setShareId(link.id);
                setShareToken(link.token);
              });
            }}
          >
            Share
          </button>
          {shareToken ? <p>Share token {shareToken}</p> : null}
          {shareId ? (
            <button
              type="button"
              onClick={() => {
                void api(`/api/v1/share-links/${shareId}:revoke`, {
                  method: "POST",
                }).then(() => setShareToken("revoked"));
              }}
            >
              Revoke share
            </button>
          ) : null}
        </header>
        <div aria-live="polite" ref={liveRef}>
          {history
            .filter((message) => message.archived)
            .map((message) => (
              <details key={message.id}>
                <summary>Previous answer</summary>
                {message.parts.map((part, index) => (
                  <RichText key={index} text={part.content || ""} />
                ))}
              </details>
            ))}
          {history
            .filter((message) => !message.archived)
            .map((message) => (
              <article key={message.id}>
                {message.parts
                  .filter((part) => part.kind === "reasoning")
                  .map((part, index) => (
                    <details key={`r-${index}`}>
                      <summary>Reasoning</summary>
                      <p>{part.content}</p>
                    </details>
                  ))}
                {message.parts
                  .filter((part) => part.kind !== "reasoning")
                  .map((part, index) => (
                    <RichText key={index} text={part.content || ""} />
                  ))}
                {message.status === "stopped" ? (
                  <p>Stopped. Partial output was kept.</p>
                ) : null}
                {message.error_code ? (
                  <ErrorNotice
                    code={message.error_code}
                    detail={message.parts
                      .map((part) => part.content || "")
                      .join(" ")}
                  />
                ) : null}
              </article>
            ))}
          {reasoning ? (
            <details>
              <summary>Reasoning</summary>
              <p>{reasoning}</p>
            </details>
          ) : null}
          {text ? <RichText text={text} /> : null}
          {approval ? (
            <article className="card">
              <h2>{approval.headline}</h2>
              {approval.flagged ? (
                <p>From untrusted input: {approval.flagged}</p>
              ) : null}
              <button type="button" onClick={() => void decide("approve")}>
                Approve
              </button>
              <button type="button" onClick={() => void decide("reject")}>
                Reject
              </button>
            </article>
          ) : null}
          {error ? (
            <ErrorNotice
              code={error.code}
              detail={error.detail}
              requestId={error.requestId}
            />
          ) : null}
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
          {streaming ? (
            <button type="button" onClick={() => void stop()}>
              Stop
            </button>
          ) : (
            <button type="button" onClick={() => void send()}>
              Send
            </button>
          )}
          {lastAssistant ? (
            <button
              type="button"
              onClick={() => void regenerate(lastAssistant.id)}
            >
              Regenerate
            </button>
          ) : null}
        </form>
      </div>
      <ArtifactPanel chatId={chatId} />
    </section>
  );
}
