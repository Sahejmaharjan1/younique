export default async function PrivacyPage({ params }: { params: Promise<{ version: string }> }) {
  const { version } = await params;
  return (
    <main className="panel">
      <h1>Privacy {version}</h1>
      <p>Provider keys and connector tokens stay encrypted. The app never returns key material.</p>
    </main>
  );
}
