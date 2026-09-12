"use client";

import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { createClient } from "@/lib/supabase/client";

/** Session state for client pages: loading → session or null. */
export function useSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
    });
    return () => subscription.unsubscribe();
  }, []);

  return { session, loading, accessToken: session?.access_token ?? null };
}
