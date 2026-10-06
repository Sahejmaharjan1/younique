import { ConsentGate } from "@/features/auth/ConsentGate";

export default function ConsentPage() {
  return (
    <main className="panel">
      <h1>Accept the current terms</h1>
      <ConsentGate />
    </main>
  );
}
