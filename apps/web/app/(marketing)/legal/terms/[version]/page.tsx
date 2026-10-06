export default async function TermsPage({
  params,
}: {
  params: Promise<{ version: string }>;
}) {
  const { version } = await params;
  return (
    <main className="panel">
      <h1>Terms {version}</h1>
      <p>
        These terms are versioned. Accepting them records the content hash shown
        in your account.
      </p>
    </main>
  );
}
