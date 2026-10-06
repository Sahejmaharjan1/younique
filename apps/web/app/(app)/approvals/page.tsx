"use client";

import { useEffect, useState } from "react";
import { ApprovalCard } from "@/features/approvals/ApprovalCard";
import { api } from "@/lib/api";

type Approval = {
  id: string;
  tool_key: string;
  summary: { headline?: string; flagged_args?: string[] };
};

export default function ApprovalsPage() {
  const [rows, setRows] = useState<Approval[]>([]);
  useEffect(() => {
    void api<{ data: Approval[] }>("/api/v1/approvals?status=pending").then(
      (body) => setRows(body.data),
    );
  }, []);
  return (
    <main>
      <h1>Approvals</h1>
      {rows.map((row) => (
        <ApprovalCard
          key={row.id}
          headline={row.summary.headline ?? row.tool_key}
          flagged={row.summary.flagged_args ?? []}
          onDecide={(decision) => {
            void api(`/api/v1/approvals/${row.id}:decide`, {
              method: "POST",
              body: JSON.stringify({ decision }),
            });
          }}
        />
      ))}
    </main>
  );
}
