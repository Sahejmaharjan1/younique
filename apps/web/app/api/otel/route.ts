export async function POST(request: Request) {
  const body = await request.text();
  return new Response(body, { status: 202 });
}
