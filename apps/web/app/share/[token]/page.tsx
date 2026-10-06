import { ShareView } from "@/features/share/ShareView";

export default async function SharePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return (
    <main className="panel">
      <meta name="robots" content="noindex, nofollow" />
      <h1>Shared chat</h1>
      <ShareView token={token} />
    </main>
  );
}
