"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { createClient } from "@/lib/supabase/client";

export function RegisterForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    const supabase = createClient();
    const { data, error: authError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: `${window.location.origin}/login`,
      },
    });
    setBusy(false);
    if (authError) {
      setError(authError.message);
      return;
    }
    // Two outcomes, both correct: email confirmation on → check the inbox;
    // off → a live session exists and we land in the shell.
    const { data: sessionData } = await supabase.auth.getSession();
    if (sessionData.session) {
      router.push("/org");
      router.refresh();
      return;
    }
    if (data.user && data.user.identities && data.user.identities.length === 0) {
      setMessage("An account with this email already exists. Try signing in.");
      return;
    }
    setMessage("Check your email to confirm the address, then sign in.");
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Email">
        <Input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </Field>
      <Field label="Password">
        <Input
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </Field>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      {message ? <p className="text-sm text-gray-700">{message}</p> : null}
      <Button type="submit" disabled={busy} className="w-full">
        {busy ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
