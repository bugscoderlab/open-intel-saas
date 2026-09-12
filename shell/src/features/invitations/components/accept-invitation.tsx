"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { ApiError, acceptInvitation, previewInvitation } from "@/lib/api/client";
import type { InvitationPreview } from "@/lib/api/types";
import { createClient } from "@/lib/supabase/client";

type State =
  | { kind: "loading" }
  | { kind: "invalid"; reason: string }
  | { kind: "ready"; preview: InvitationPreview }
  | { kind: "accepted" }
  | { kind: "error"; message: string };

/** Accept page reached from the emailed link
 *  (ticket #19: /invitations/accept?token=…). */
export function AcceptInvitation({ token }: { token: string }) {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [sessionEmail, setSessionEmail] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    previewInvitation(token)
      .then((preview) => {
        if (!cancelled) setState({ kind: "ready", preview });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setState({
          kind: "invalid",
          reason:
            cause instanceof ApiError && cause.status === 410
              ? "This invitation has expired or was already used."
              : "This invitation link is invalid.",
        });
      });
    createClient()
      .auth.getSession()
      .then(({ data }) => {
        if (!cancelled) setSessionEmail(data.session?.user.email ?? null);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function accept() {
    const {
      data: { session },
    } = await createClient().auth.getSession();
    if (!session) {
      router.push(`/login?next=/invitations/accept?token=${token}`);
      return;
    }
    setBusy(true);
    try {
      await acceptInvitation(session.access_token, token);
      setState({ kind: "accepted" });
    } catch (cause) {
      setState({
        kind: "error",
        message:
          cause instanceof ApiError && cause.status === 403
            ? "This invitation is for a different email address. Sign in with the invited email, then reopen the link."
            : cause instanceof Error
              ? cause.message
              : "Accepting failed",
      });
    } finally {
      setBusy(false);
    }
  }

  if (state.kind === "loading") {
    return <p className="text-sm text-gray-500">Loading invitation…</p>;
  }

  if (state.kind === "invalid") {
    return (
      <Card>
        <CardTitle>Invitation unavailable</CardTitle>
        <p className="text-sm text-gray-700">{state.reason}</p>
        <p className="mt-3 text-sm">
          <Link href="/login" className="text-blue-600 hover:underline">
            Sign in
          </Link>
        </p>
      </Card>
    );
  }

  if (state.kind === "accepted") {
    return (
      <Card>
        <CardTitle>You are in</CardTitle>
        <p className="text-sm text-gray-700">
          The invitation was accepted. Open your organization to continue.
        </p>
        <p className="mt-3">
          <Link href="/org">
            <Button variant="secondary">Go to my organizations</Button>
          </Link>
        </p>
      </Card>
    );
  }

  const preview = state.kind === "ready" ? state.preview : null;
  const mismatch =
    preview != null &&
    sessionEmail != null &&
    sessionEmail.toLowerCase() !== preview.email.toLowerCase();

  return (
    <Card>
      <CardTitle>Invitation to {preview?.organization_name}</CardTitle>
      {preview ? (
        <p className="text-sm text-gray-700">
          You have been invited as{" "}
          <span className="font-medium">{preview.role}</span> (
          {preview.scope} scope) at {preview.email}.
        </p>
      ) : null}
      {mismatch ? (
        <p className="mt-3 rounded-md bg-amber-50 p-3 text-sm text-amber-800">
          You are signed in as {sessionEmail}, but this invitation is for{" "}
          {preview?.email}. Sign in with the invited email to accept.
        </p>
      ) : null}
      {state.kind === "error" ? (
        <p className="mt-3 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {state.message}
        </p>
      ) : null}
      <div className="mt-4 flex gap-2">
        <Button onClick={accept} disabled={busy || mismatch === true}>
          {busy ? "Accepting…" : "Accept invitation"}
        </Button>
        <Link href="/login">
          <Button variant="secondary">Sign in / Register</Button>
        </Link>
      </div>
    </Card>
  );
}
