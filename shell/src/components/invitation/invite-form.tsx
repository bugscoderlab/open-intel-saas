"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { ApiError, inviteMember } from "@/lib/api/client";

interface InviteFormProps {
  accessToken: string;
  organizationId: string;
  scope: "organization" | "team" | "project";
  /** Role choices depend on scope (matrix: org member|admin, team
   *  manager|member, project editor|viewer). */
  roles: Array<{ value: string; label: string }>;
  teamId?: string;
  projectId?: string;
  onInvited?: () => void;
}

/** Invite-by-email form; the backend emails the accept link
 *  (ticket #19 invitation flow). */
export function InviteForm({
  accessToken,
  organizationId,
  scope,
  roles,
  teamId,
  projectId,
  onInvited,
}: InviteFormProps) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(roles[0]?.value ?? "member");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await inviteMember(accessToken, organizationId, {
        email,
        scope,
        role,
        team_id: teamId,
        project_id: projectId,
      });
      setMessage(`Invitation sent to ${email} as ${role}.`);
      setEmail("");
      onInvited?.();
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 403
          ? "You are not allowed to invite at this scope."
          : cause instanceof Error
            ? cause.message
            : "Invitation failed",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <Field label="Invite by email">
            <Input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="teammate@example.com"
            />
          </Field>
        </div>
        <div>
          <Field label="Role">
            <select
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
              value={role}
              onChange={(event) => setRole(event.target.value)}
            >
              {roles.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Button type="submit" disabled={busy}>
          {busy ? "Sending…" : "Invite"}
        </Button>
      </div>
      {message ? <p className="text-sm text-green-700">{message}</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
    </form>
  );
}
