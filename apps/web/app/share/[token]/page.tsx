export default async function SharePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <main className="panel">
      <meta name="robots" content="noindex, nofollow" />
      <h1>Shared chat</h1>
      <p>Token {token}. Reasoning stays hidden unless the owner enabled it on the link.</p>
    </main>
  );
}
