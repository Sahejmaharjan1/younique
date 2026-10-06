import Link from "next/link";
import type { ReactNode } from "react";
import { AccountSwitcher } from "@/features/auth/AccountSwitcher";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <strong>Younique</strong>
        <nav>
          <p>
            <Link href="/chat/new">New chat</Link>
          </p>
          <p>
            <Link href="/artifacts">Artifacts</Link>
          </p>
          <p>
            <Link href="/connections">Connections</Link>
          </p>
          <p>
            <Link href="/approvals">Approvals</Link>
          </p>
          <p>
            <Link href="/usage">Usage</Link>
          </p>
          <p>
            <Link href="/settings/keys">Keys</Link>
          </p>
          <p>
            <Link href="/settings/sessions">Sessions</Link>
          </p>
          <p>
            <Link href="/settings/tool-policies">Tool policy</Link>
          </p>
        </nav>
        <AccountSwitcher />
      </aside>
      <div className="panel">{children}</div>
    </div>
  );
}
