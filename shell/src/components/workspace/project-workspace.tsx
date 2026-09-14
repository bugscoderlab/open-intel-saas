"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

import { ProjectMembersPanel } from "@/features/projects/components/project-members-panel";
import { TagsPanel } from "@/features/tags/components/tags-panel";
import { CompetitorsView } from "@/features/competitors/components/competitors-view";
import { OverviewView } from "@/features/competitors/components/overview-view";
import { ReviewView } from "@/features/competitors/components/review-view";
import { NotebooksView } from "@/features/research/components/notebooks-view";
import { SearchView } from "@/features/research/components/search-view";
import { SourcesView } from "@/components/workspace/sources-view";
import { WorkspaceShell, type WorkspaceNavItem } from "@/components/layout/workspace-shell";
import { Badge } from "@/components/ui/badge";
import { card } from "@/components/workspace/bits";
import {
  getMe,
  getProject,
  listCompetitors,
  listEvidence,
  listLocations,
  listMembers,
  listNotebooks,
  listNotes,
  listObservations,
  listOrganizations,
  listProjectMembers,
  listServices,
  listSources,
  listTeamMembers,
  listTags,
  reviewQueue,
} from "@/lib/api/client";
import type {
  Competitor,
  EvidenceLink,
  Location,
  Member,
  Note,
  Notebook,
  Observation,
  Organization,
  Project,
  ProjectMember,
  ProjectTag,
  Service,
  Source,
  TeamMember,
} from "@/lib/api/types";
import { useSession } from "@/lib/auth/use-session";

/** The views of the unified project workspace (PDR-004: one workspace per
 *  project — the notebook and the competitor-intelligence views are views
 *  inside it, never separate workspaces). The active view is deep-linked
 *  via the `?view=` query param. */
const VIEWS = [
  "overview",
  "competitors",
  "review",
  "notebooks",
  "sources",
  "search",
  "manage",
] as const;
type View = (typeof VIEWS)[number];

function isView(value: string | null): value is View {
  return VIEWS.includes(value as View);
}

const NAV: { key: View; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "competitors", label: "Competitors" },
  { key: "review", label: "Review queue" },
  { key: "notebooks", label: "Notebooks" },
  { key: "sources", label: "Sources" },
  { key: "search", label: "Search" },
  { key: "manage", label: "Manage" },
];

/** Unified project workspace (spec #36, ticket #37): single chrome, single
 *  navigation, hosting the market overview, competitor directory, review
 *  queue, notebooks, sources, search, and project management. */
export function ProjectWorkspace() {
  const params = useParams<{ orgId: string; projectId: string }>();
  const orgId = params.orgId;
  const projectId = params.projectId;
  const router = useRouter();
  const searchParams = useSearchParams();
  const { accessToken, session } = useSession();

  const view: View = isView(searchParams.get("view"))
    ? (searchParams.get("view") as View)
    : "overview";
  /** Deep link into the notebook detail (Notebooks view only). */
  const activeNotebookId = searchParams.get("notebook");

  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [orgMembers, setOrgMembers] = useState<Member[]>([]);
  const [projectMembers, setProjectMembers] = useState<ProjectMember[]>([]);
  const [owningTeamMembers, setOwningTeamMembers] = useState<TeamMember[]>([]);
  const [tags, setTags] = useState<ProjectTag[]>([]);
  const [meId, setMeId] = useState<string | null>(null);

  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [notesByNotebook, setNotesByNotebook] = useState<Record<string, Note[]>>({});

  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [queue, setQueue] = useState<Observation[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [locationsByCompetitor, setLocationsByCompetitor] = useState<
    Record<string, Location[]>
  >({});
  const [observationsByCompetitor, setObservationsByCompetitor] = useState<
    Record<string, Observation[]>
  >({});
  const [evidenceByCompetitor, setEvidenceByCompetitor] = useState<
    Record<string, EvidenceLink[]>
  >({});

  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!accessToken) return;
    setError(null);
    try {
      const [me, orgList, projectRow, memberList, projectMemberList, tagList] =
        await Promise.all([
          getMe(accessToken),
          listOrganizations(accessToken),
          getProject(accessToken, projectId),
          listMembers(accessToken, orgId),
          listProjectMembers(accessToken, projectId),
          listTags(accessToken, projectId),
        ]);
      setOrgs(orgList);
      setProject(projectRow);
      setOrgMembers(memberList);
      setProjectMembers(projectMemberList);
      setTags(tagList);
      setMeId(me.app_user_id);
      if (projectRow.owning_team_id) {
        setOwningTeamMembers(
          await listTeamMembers(accessToken, projectRow.owning_team_id),
        );
      } else {
        setOwningTeamMembers([]);
      }

      const [notebookList, sourceList, competitorList, serviceList, queueList] =
        await Promise.all([
          listNotebooks(accessToken, projectId),
          listSources(accessToken, projectId),
          listCompetitors(accessToken, projectId),
          listServices(accessToken, projectId),
          reviewQueue(accessToken, projectId),
        ]);
      setNotebooks(notebookList);
      setSources(sourceList);
      setCompetitors(competitorList);
      setServices(serviceList);
      setQueue(queueList);

      const perNotebook = await Promise.all(
        notebookList.map(async (notebook) => ({
          notebook,
          notes: await listNotes(accessToken, projectId, notebook.id),
        })),
      );
      setNotesByNotebook(
        Object.fromEntries(perNotebook.map((r) => [r.notebook.id, r.notes])),
      );

      const perCompetitor = await Promise.all(
        competitorList.map(async (competitor) => {
          const [locations, observations, evidence] = await Promise.all([
            listLocations(accessToken, projectId, competitor.id),
            listObservations(accessToken, projectId, competitor.id),
            listEvidence(accessToken, projectId, competitor.id),
          ]);
          return { competitor, locations, observations, evidence };
        }),
      );
      setLocationsByCompetitor(
        Object.fromEntries(perCompetitor.map((r) => [r.competitor.id, r.locations])),
      );
      setObservationsByCompetitor(
        Object.fromEntries(perCompetitor.map((r) => [r.competitor.id, r.observations])),
      );
      setEvidenceByCompetitor(
        Object.fromEntries(perCompetitor.map((r) => [r.competitor.id, r.evidence])),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load workspace");
    }
  }, [accessToken, orgId, projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const onNav = useCallback(
    (key: string) => {
      const next = isView(key) ? key : "overview";
      router.replace(`/org/${orgId}/projects/${projectId}?view=${next}`, {
        scroll: false,
      });
    },
    [orgId, projectId, router],
  );

  const onSelectNotebook = useCallback(
    (notebookId: string | null) => {
      const qs = new URLSearchParams({ view: "notebooks" });
      if (notebookId) qs.set("notebook", notebookId);
      router.replace(`/org/${orgId}/projects/${projectId}?${qs.toString()}`, {
        scroll: false,
      });
    },
    [orgId, projectId, router],
  );

  if (!accessToken || !session) return null;

  // Matrix mirror, same derivation as the former project detail page: org
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
    (project?.owning_team_id != null && myTeamRole === "manager");
  const readOnly = !canEdit;

  const navItems: WorkspaceNavItem[] = NAV.map((item) => {
    if (item.key === "review") return { ...item, count: queue.length };
    if (item.key === "sources") return { ...item, count: sources.length };
    return item;
  });

  return (
    <WorkspaceShell
      email={session.user.email ?? ""}
      orgs={orgs}
      currentOrgId={orgId}
      crumbs={["Projects", project?.name ?? "…"]}
      navItems={navItems}
      activeNav={view}
      onNav={onNav}
    >
      {error ? (
        <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
      ) : null}

      {view === "overview" ? (
        <OverviewView
          token={accessToken}
          projectId={projectId}
          competitors={competitors}
          services={services}
          queue={queue}
          locationsByCompetitor={locationsByCompetitor}
          observationsByCompetitor={observationsByCompetitor}
          evidenceByCompetitor={evidenceByCompetitor}
          readOnly={readOnly}
          onChanged={load}
        />
      ) : null}
      {view === "competitors" ? (
        <CompetitorsView
          token={accessToken}
          projectId={projectId}
          competitors={competitors}
          locationsByCompetitor={locationsByCompetitor}
          observationsByCompetitor={observationsByCompetitor}
          evidenceByCompetitor={evidenceByCompetitor}
          services={services}
          readOnly={readOnly}
          onChanged={load}
        />
      ) : null}
      {view === "review" ? (
        <ReviewView
          token={accessToken}
          projectId={projectId}
          queue={queue}
          competitors={competitors}
          services={services}
          readOnly={readOnly}
          onChanged={load}
        />
      ) : null}
      {view === "notebooks" ? (
        <NotebooksView
          token={accessToken}
          projectId={projectId}
          notebooks={notebooks}
          notesByNotebook={notesByNotebook}
          sources={sources}
          activeNotebookId={activeNotebookId}
          readOnly={readOnly}
          onSelectNotebook={onSelectNotebook}
          onChanged={load}
        />
      ) : null}
      {view === "sources" ? (
        <SourcesView
          token={accessToken}
          projectId={projectId}
          notebooks={notebooks}
          sources={sources}
          competitors={competitors}
          evidenceByCompetitor={evidenceByCompetitor}
          readOnly={readOnly}
          onChanged={load}
        />
      ) : null}
      {view === "search" ? <SearchView token={accessToken} projectId={projectId} /> : null}
      {view === "manage" && project ? (
        <ManageView
          accessToken={accessToken}
          orgId={orgId}
          project={project}
          projectId={projectId}
          tags={tags}
          projectMembers={projectMembers}
          orgMembers={orgMembers}
          currentUserId={meId ?? ""}
          canEdit={canEdit}
          onChanged={load}
        />
      ) : null}
    </WorkspaceShell>
  );
}

/** Project administration: identity badges, tags, and members — the content
 *  of the former standalone project detail page, now a workspace view. */
function ManageView({
  accessToken,
  orgId,
  project,
  projectId,
  tags,
  projectMembers,
  orgMembers,
  currentUserId,
  canEdit,
  onChanged,
}: {
  accessToken: string;
  orgId: string;
  project: Project;
  projectId: string;
  tags: ProjectTag[];
  projectMembers: ProjectMember[];
  orgMembers: Member[];
  currentUserId: string;
  canEdit: boolean;
  onChanged: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-base font-semibold text-gray-900">{project.name}</span>
        {project.owning_team_id ? (
          <Badge tone="blue">team-owned</Badge>
        ) : (
          <Badge tone="gray">organization-owned</Badge>
        )}
        <Badge tone="gray">{project.visibility}</Badge>
        <Badge tone={canEdit ? "green" : "amber"}>{canEdit ? "editor" : "viewer"}</Badge>
      </div>
      <div className={`${card} space-y-3`}>
        <h3 className="text-sm font-semibold text-gray-900">Tags</h3>
        <TagsPanel
          accessToken={accessToken}
          projectId={projectId}
          tags={tags}
          canEdit={canEdit}
          onChanged={onChanged}
        />
      </div>
      <div className={`${card} space-y-3`}>
        <h3 className="text-sm font-semibold text-gray-900">Members</h3>
        <ProjectMembersPanel
          accessToken={accessToken}
          organizationId={orgId}
          projectId={projectId}
          projectMembers={projectMembers}
          orgMembers={orgMembers}
          currentUserId={currentUserId}
          canInvite={canEdit}
          onChanged={onChanged}
        />
      </div>
    </div>
  );
}
