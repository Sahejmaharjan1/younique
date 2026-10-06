export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("content-type") && init.body) headers.set("content-type", "application/json");
  const csrf = document.cookie
    .split("; ")
    .find((part) => part.startsWith("csrf="))
    ?.split("=")[1];
  if (csrf) headers.set("x-csrf-token", decodeURIComponent(csrf));
  if (init.method && init.method !== "GET" && !headers.has("idempotency-key")) {
    headers.set("idempotency-key", crypto.randomUUID());
  }
  const response = await fetch(path, { ...init, headers, credentials: "include" });
  if (!response.ok && response.headers.get("content-type")?.includes("json")) {
    const problem = (await response.json()) as { code?: string; detail?: string };
    throw new Error(problem.detail ?? problem.code ?? response.statusText);
  }
  if (response.status === 204) return undefined as T;
  const type = response.headers.get("content-type") ?? "";
  if (type.includes("text/event-stream")) return response as T;
  return (await response.json()) as T;
}
