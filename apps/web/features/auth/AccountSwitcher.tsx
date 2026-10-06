"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Me = { user_id: string; workspace_id: string; role: string };

export function AccountSwitcher() {
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    void api<Me>("/api/v1/me").then(setMe);
  }, []);
  return (
    <p>
      Account {me?.user_id ?? "…"} · workspace {me?.workspace_id ?? "…"} · {me?.role ?? ""}
    </p>
  );
}
