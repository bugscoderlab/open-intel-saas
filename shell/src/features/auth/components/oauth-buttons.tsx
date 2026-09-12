"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";

/** OAuth through Supabase Auth (works once a provider is configured in the
 *  project; the button reports the error visibly otherwise). */
export function OAuthButtons() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signInWith(provider: "google") {
    setBusy(true);
    setError(null);
    const { error: authError } = await createClient().auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    setBusy(false);
    if (authError) setError(authError.message);
  }

  return (
    <div className="space-y-2">
      <Button
        variant="secondary"
        className="w-full"
        disabled={busy}
        onClick={() => signInWith("google")}
      >
        Continue with Google
      </Button>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
    </div>
  );
}
