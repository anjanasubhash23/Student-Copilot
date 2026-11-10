"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError, type User } from "@/lib/api";

// Wraps signed-in pages: fetches the current user, sends anyone signed out to /login.
export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace("/login");
      });
  }, [router]);

  if (!user) return <div className="p-8 text-sm text-muted">Loading…</div>;

  return (
    <div className="min-h-screen">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link href="/" className="font-semibold">
            Study Copilot
          </Link>
          <div className="flex items-center gap-3 text-sm text-ink-2">
            <span className="hidden sm:inline">{user.email}</span>
            <button
              className="btn-ghost"
              onClick={async () => {
                await api.logout();
                router.replace("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}
