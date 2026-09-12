"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { useSession } from "@/lib/auth/use-session";

/** Client pages wrap themselves with this: unauthenticated visitors are
 *  redirected to /login (ticket #19: "unauthenticated visitors only ever
 *  see register/login"). */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !session) router.replace("/login");
  }, [loading, session, router]);

  if (loading || !session) {
    return <p className="p-8 text-sm text-gray-500">Loading…</p>;
  }
  return <>{children}</>;
}
