import { NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";

/** OAuth redirect target: exchanges the auth code for a session, then
 *  lands in the shell. */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}/org`);
    }
  }
  return NextResponse.redirect(`${origin}/login?error=oauth`);
}
