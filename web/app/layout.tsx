import type { Metadata } from "next";

import "katex/dist/katex.min.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Study Copilot",
  description: "A tutor that knows what you've mastered.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
