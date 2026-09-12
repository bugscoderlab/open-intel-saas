"use client";

import { createBrowserClient } from "@supabase/ssr";

import { env } from "@/lib/env";

/** Browser Supabase client (cookie-backed session, shared with SSR). */
export function createClient() {
  return createBrowserClient(env.supabaseUrl, env.supabaseAnonKey);
}
