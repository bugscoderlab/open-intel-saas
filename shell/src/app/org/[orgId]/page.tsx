"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { RequireAuth } from "@/components/layout/require-auth";
import { InviteForm } from "@/components/invitation/invite-form";
import { Card } from "@/components/ui/card";
import { MembersPanel } from "@/features/organizations/components/members-panel";
import { ProjectsPanel } from "@/features/projects/components/projects-panel";
import { TeamsPanel } from "@/features/teams/components/teams-panel";
import { useSession } from "@/lib/auth/use-session";
import {
  getMe,
  listMembers,
  listOrganizations,
  listProjects,
  listTeams,
} from "@/lib/api/client";
import type { Member, Organization, Project, Team } from "@/lib/api/types";

export default function OrgDashboardPage() {
  return (
    <RequireAuth>
      <OrgDashboard />
    </RequireAuth>
  );
}

function OrgDashboard() {
  const params = useParams<{ orgId: string }>();
  const orgId = params.orgId;
  const { accessToken, session } = useSession();

  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [meId, setMeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [me, orgList, memberList, teamList, projectList] =
        await Promise.all([
          getMe(accessToken),
          listOrganizations(accessToken),
          listMembers(accessToken, orgId),
          listTeams(accessToken, orgId),
          listProjects(accessToken, orgId),
        ]);
      setMeId(me.app_user_id);
      setOrgs(orgList);
      setMembers(memberList);
      setTeams(teamList);
      setProjects(projectList);
      setError(null);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Failed to load the organization",
      );
    }
  }, [accessToken, orgId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!accessToken || !session) return null;

  const myRole = members.find((member) => member.app_user_id === meId)?.role;
  const isOrgManager = myRole === "owner" || myRole === "admin";
  const isMember = myRole != null;

  if (error === "Not Found" || (members.length === 0 && !isMember && orgs.length > 0)) {
    return (
      <main className="mx-auto max-w-md px-4 py-12">
        <Card>
          <p className="text-sm text-gray-700">
            This organization does not exist or you are not a member of it.
          </p>
        </Card>
      </main>
    );
  }

  return (
    <AppShell
      email={session.user.email ?? ""}
      orgs={orgs}
      currentOrgId={orgId}
    >
      {error ? (
        <Card>
          <p className="text-sm text-red-600">{error}</p>
        </Card>
      ) : null}
      <MembersPanel members={members} currentUserId={meId ?? ""} />
      {isOrgManager ? (
        <Card>
          <InviteForm
            accessToken={accessToken}
            organizationId={orgId}
            scope="organization"
            roles={[
              { value: "member", label: "Member" },
              { value: "admin", label: "Admin" },
            ]}
          />
        </Card>
      ) : null}
      <TeamsPanel
        accessToken={accessToken}
        organizationId={orgId}
        teams={teams}
        members={members}
        currentUserId={meId ?? ""}
        isOrgManager={isOrgManager}
        onChanged={load}
      />
      <ProjectsPanel
        accessToken={accessToken}
        organizationId={orgId}
        projects={projects}
        teams={teams}
        onChanged={load}
      />
    </AppShell>
  );
}
