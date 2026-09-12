"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardTitle } from "@/components/ui/card";
import { InviteForm } from "@/components/invitation/invite-form";
import type { Member, ProjectMember } from "@/lib/api/types";

interface ProjectMembersPanelProps {
  accessToken: string;
  organizationId: string;
  projectId: string;
  projectMembers: ProjectMember[];
  /** Org-wide member list (project members carry no email). */
  orgMembers: Member[];
  currentUserId: string;
  /** Org admins/owneers or project editors can invite (matrix). */
  canInvite: boolean;
  onChanged: () => void;
}

export function ProjectMembersPanel({
  accessToken,
  organizationId,
  projectId,
  projectMembers,
  orgMembers,
  currentUserId,
  canInvite,
  onChanged,
}: ProjectMembersPanelProps) {
  const emailById = new Map(
    orgMembers.map((member) => [member.app_user_id, member.email]),
  );

  return (
    <Card>
      <CardTitle>Project members</CardTitle>
      <ul className="mb-3 divide-y divide-gray-100">
        {projectMembers.map((member) => (
          <li key={member.app_user_id} className="flex items-center justify-between py-2">
            <span className="text-sm text-gray-900">
              {emailById.get(member.app_user_id) ?? member.app_user_id}
              {member.app_user_id === currentUserId ? " (you)" : ""}
            </span>
            <Badge tone={member.role === "editor" ? "blue" : "gray"}>
              {member.role}
            </Badge>
          </li>
        ))}
        {projectMembers.length === 0 ? (
          <li className="py-2 text-sm text-gray-500">
            No direct members — access comes from the owning team or
            organization role.
          </li>
        ) : null}
      </ul>
      {canInvite ? (
        <InviteForm
          accessToken={accessToken}
          organizationId={organizationId}
          scope="project"
          roles={[
            { value: "editor", label: "Editor" },
            { value: "viewer", label: "Viewer" },
          ]}
          projectId={projectId}
          onInvited={onChanged}
        />
      ) : (
        <p className="text-xs text-gray-500">
          Only project editors can invite project members.
        </p>
      )}
    </Card>
  );
}
