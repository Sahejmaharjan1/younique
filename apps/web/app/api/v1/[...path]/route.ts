import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, path: string[]) {
  const origin = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";
  const url = new URL(request.url);
  const target = `${origin}/v1/${path.join("/")}${url.search}`;
  const headers = new Headers(request.headers);
  headers.delete("host");
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
    init.duplex = "half";
  }
  const response = await fetch(target, init);
  const outgoing = new Headers(response.headers);
  outgoing.delete("content-length");
  outgoing.set("x-younique-proxy", "route");
  return new Response(response.body, {
    status: response.status,
    headers: outgoing,
  });
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function POST(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function PUT(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function PATCH(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function DELETE(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}
