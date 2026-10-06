export type SseEvent = { id: string; event: string; data: string };

export async function* readSse(response: Response): AsyncGenerator<SseEvent> {
  const body = response.body;
  if (!body) return;
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const lastId = { current: "" };
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const parsed = parseFrame(frame);
      if (parsed) {
        lastId.current = parsed.id;
        yield parsed;
      }
    }
  }
  if (buffer.trim()) {
    const parsed = parseFrame(buffer);
    if (parsed) yield parsed;
  }
}

export function parseFrame(frame: string): SseEvent | null {
  let id = "";
  let event = "message";
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("id:")) id = line.slice(3).trim();
    else if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (!id && data.length === 0) return null;
  return { id, event, data: data.join("\n") };
}

export async function resume(runId: string, lastEventId: string): Promise<Response> {
  const response = await fetch(`/api/v1/runs/${runId}/events?last_event_id=${lastEventId}`, {
    headers: { accept: "text/event-stream" },
  });
  return response;
}
