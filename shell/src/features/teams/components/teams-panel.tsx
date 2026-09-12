"use client";

import { useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { createTeam, listTeamMembers } from "@/lib/api/client";
import type { Member, Team, TeamMember } from "@/lib/api/types";

import { InviteForm } from "@/components/invitation/invite-form";

interface TeamsPanelProps {
  accessToken: string;
  organizationId: string;
  teams: Team[];
  members: Member[];
  currentUserId: string;
  /** Org admins/owners manage every team (matrix, not role names). */
  isOrgManager: boolean;
  onChanged: () => void;
}

/** Team management: any member creates; manager capabilities only for
 *  team managers and org admins/owners (ticket #20). */
export function TeamsPanel({
  accessToken,
  organizationId,
  teams,
  members,
  currentUserId,
  isOrgManager,
  onChanged,
}: TeamsPanelProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createTeam(accessToken, organizationId, name);
      setName("");
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to create team");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>Teams</CardTitle>
      <ul className="mb-4 divide-y divide-gray-100">
        {teams.map((team) => (
          <TeamRow
            key={team.id}
            accessToken={accessToken}
            organizationId={organizationId}
            team={team}
            members={members}
            currentUserId={currentUserId}
            isOrgManager={isOrgManager}
          />
        ))}
        {teams.length === 0 ? (
          <li className="py-2 text-sm text-gray-500">No teams yet.</li>
        ) : null}
      </ul>
      <form onSubmit={submit} className="flex items-end gap-2">
        <div className="flex-1">
          <Field label="New team">
            <Input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Competitive research"
            />
          </Field>
        </div>
        <Button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create team"}
        </Button>
      </form>
      {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}
    </Card>
  );
}

function TeamRow({
  accessToken,
  organizationId,
  team,
  members,
  currentUserId,
  isOrgManager,
}: {
  accessToken: string;
  organizationId: string;
  team: Team;
  members: Member[];
  currentUserId: string;
  isOrgManager: boolean;
}) {
  const [teamMembers, setTeamMembers] = useState<TeamMember[] | null>(null);
  const [open, setOpen] = useState(false);

  const emailById = new Map(members.map((member) => [member.app_user_id, member.email]));

  async function toggle() {
    if (!open) {
      setTeamMembers(await listTeamMembers(accessToken, team.id));
      setOpen(true);
    } else {
      setOpen(false);
    }
  }

  const me = teamMembers?.find((member) => member.app_user_id === currentUserId);
  const canInvite = isOrgManager || me?.role === "manager";

  return (
    <li className="py-2">
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={toggle}
          className="text-sm font-medium text-gray-900 hover:underline"
        >
          {team.name}
        </button>
        <Badge tone="gray" className="cursor-pointer" >
          <button type="button" onClick={toggle}>
            {open ? "hide" : "members"}
          </button>
        </Badge>
      </div>
      {open && teamMembers ? (
        <div className="mt-2 space-y-2 pl-4">
          <ul className="space-y-1">
            {teamMembers.map((member) => (
              <li key={member.app_user_id} className="flex justify-between text-sm">
                <span className="text-gray-700">
                  {emailById.get(member.app_user_id) ?? member.app_user_id}
                  {member.app_user_id === currentUserId ? " (you)" : ""}
                </span>
                <Badge tone={member.role === "manager" ? "blue" : "gray"}>
                  {member.role}
                </Badge>
              </li>
            ))}
          </ul>
          {canInvite ? (
            <InviteForm
              accessToken={accessToken}
              organizationId={organizationId}
              scope="team"
              roles={[
                { value: "member", label: "Team member" },
                { value: "manager", label: "Team manager" },
              ]}
              teamId={team.id}
              onInvited={async () => setTeamMembers(await listTeamMembers(accessToken, team.id))}
            />
          ) : (
            <p className="text-xs text-gray-500">
              Only team managers can invite to this team.
            </p>
          )}
        </div>
      ) : null}
    </li>
  );
}
