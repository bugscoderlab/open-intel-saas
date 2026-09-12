/** Client-safe environment (all NEXT_PUBLIC_). */

export const env = {
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
  /** FastAPI platform backend (dev default; CORS is wide-open, see AGENTS.md). */
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:5055",
} as const;
