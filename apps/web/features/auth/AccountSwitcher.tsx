"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Me = { user_id: string; workspace_id: string; role: string };
type Account = { user_id: string; is_current: boolean };

export function AccountSwitcher() {
  const [me, setMe] = useState<Me | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  useEffect(() => {
    void api<Me>("/api/v1/me").then(setMe);
    void api<{ data: Account[] }>("/api/v1/auth/accounts").then((body) =>
      setAccounts(body.data),
    );
  }, []);

  function switchTo(userId: string) {
    window.localStorage.setItem("younique.accountId", userId);
    window.location.reload();
  }

  return (
    <div>
      <p>
        Account {me?.user_id ?? "…"} · workspace {me?.workspace_id ?? "…"} ·{" "}
        {me?.role ?? ""}
      </p>
      {accounts.map((account) => (
        <button
          key={account.user_id}
          type="button"
          onClick={() => switchTo(account.user_id)}
        >
          {account.is_current ? "Current" : "Switch"} {account.user_id}
        </button>
      ))}
    </div>
  );
}
