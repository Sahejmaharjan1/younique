import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Younique",
  description: "An AI workspace that acts in the services you already use.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
