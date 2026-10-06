import Link from "next/link";

export default function LandingPage() {
  return (
    <main className="panel">
      <h1>Younique</h1>
      <p>Connect a service, bring your own model key, and approve what the agent does.</p>
      <p>
        <Link href="/login">Log in</Link>
      </p>
    </main>
  );
}
