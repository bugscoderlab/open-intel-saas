"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { RequireAuth } from "@/components/layout/require-auth";
import { Badge } from "@/components/ui/badge";
import { Card, CardTitle } from "@/components/ui/card";
import { ProjectMembersPanel } from "@/features/projects/components/project-members-panel";
import { TagsPanel } from "@/features/tags/components/tags-panel";
import { useSession } from "@/lib/auth/use-session";
import {
  getMe,
  getProject,
  listMembers,
  listOrganizations,
  listProjectMembers,
  listTags,
  listTeamMembers,
} from "@/lib/api/client";
import type {
  Member,
  Organization,
  Project,
  ProjectMember,
  ProjectTag,
  TeamMember,
} from "@/lib/api/types";

export default function ProjectDetailPage() {
  return (
    <RequireAuth>
      <ProjectDetail />
    </RequireAuth>
  );
}

function ProjectDetail() {
  const params = useParams<{ orgId: string; projectId: string }>();
  const { orgId, projectId } = params;
  const { accessToken, session } = useSession();

  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [orgMembers, setOrgMembers] = useState<Member[]>([]);
  const [projectMembers, setProjectMembers] = useState<ProjectMember[]>([]);
  const [owningTeamMembers, setOwningTeamMembers] = useState<TeamMember[]>([]);
  const [tags, setTags] = useState<ProjectTag[]>([]);
  const [meId, setMeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const me = await getMe(accessToken);
      setMeId(me.app_user_id);
      const orgList = await listOrganizations(accessToken);
      setOrgs(orgList);
      const [projectDetail, memberList, projectMemberList, tagList] =
        await Promise.all([
          getProject(accessToken, projectId),
          listMembers(accessToken, orgId),
          listProjectMembers(accessToken, projectId),
          listTags(accessToken, projectId),
        ]);
      setProject(projectDetail);
      setOrgMembers(memberList);
      setProjectMembers(projectMemberList);
      setTags(tagList);
      if (projectDetail.owning_team_id) {
        setOwningTeamMembers(
          await listTeamMembers(accessToken, projectDetail.owning_team_id),
        );
      }
      setError(null);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Failed to load the project",
      );
    }
  }, [accessToken, orgId, projectId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!accessToken || !session) return null;

  if (error) {
    return (
      <AppShell email={session.user.email ?? ""} orgs={orgs} currentOrgId={orgId}>
        <Card>
          <CardTitle>Project unavailable</CardTitle>
          <p className="text-sm text-red-600">{error}</p>
        </Card>
      </AppShell>
    );
  }

  if (!project) {
    return (
      <AppShell email={session.user.email ?? ""} orgs={orgs} currentOrgId={orgId}>
        <p className="text-sm text-gray-500">Loading…</p>
      </AppShell>
    );
  }

  // Matrix mirror (no role-name checks in the backend either): org
  // owner/admin get everything; project editor mutates; team manager acts
  // as editor on team projects; everyone else is a viewer.
  const orgRole = orgMembers.find((member) => member.app_user_id === meId)?.role;
  const isOrgManager = orgRole === "owner" || orgRole === "admin";
  const myProjectRole = projectMembers.find(
    (member) => member.app_user_id === meId,
  )?.role;
  const myTeamRole = owningTeamMembers.find(
    (member) => member.app_user_id === meId,
  )?.role;
  const canEdit =
    isOrgManager ||
    myProjectRole === "editor" ||
    (project.owning_team_id != null && myTeamRole === "manager");

  return (
    <AppShell email={session.user.email ?? ""} orgs={orgs} currentOrgId={orgId}>
      <Card>
        <div className="mb-1 flex items-center gap-2">
          <CardTitle className="mb-0">{project.name}</CardTitle>
          {project.owning_team_id ? (
            <Badge tone="blue">team-owned</Badge>
          ) : (
            <Badge tone="gray">organization-owned</Badge>
          )}
          <Badge tone="gray">{project.visibility}</Badge>
          <Badge tone={canEdit ? "green" : "amber"}>
            {canEdit ? "editor" : "viewer"}
          </Badge>
        </div>
        <CardTitle className="mt-4">Tags</CardTitle>
        <TagsPanel
          accessToken={accessToken}
          projectId={projectId}
          tags={tags}
          canEdit={canEdit}
          onChanged={load}
        />
      </Card>
      <ProjectMembersPanel
        accessToken={accessToken}
        organizationId={orgId}
        projectId={projectId}
        projectMembers={projectMembers}
        orgMembers={orgMembers}
        currentUserId={meId ?? ""}
        canInvite={canEdit}
        onChanged={load}
      />
    </AppShell>
  );
}
