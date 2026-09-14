import { env } from "@/lib/env";
import type {
  Competitor,
  EvidenceLink,
  Invitation,
  InvitationPreview,
  Location,
  Me,
  Member,
  Notebook,
  Note,
  Observation,
  Organization,
  Project,
  ProjectMember,
  ProjectTag,
  SearchHit,
  Service,
  Source,
  Team,
  TeamMember,
} from "@/lib/api/types";

/** Platform API (FastAPI) client. The user's Supabase access token is the
 *  bearer credential; the backend resolves identity from the JWT. */

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

async function request<T>(
  token: string | null,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${env.apiUrl}${path}`, {
    ...init,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // non-JSON error body: keep the status-based detail
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const get = <T>(token: string | null, path: string) => request<T>(token, path);
const post = <T>(token: string | null, path: string, body: unknown) =>
  request<T>(token, path, { method: "POST", body: JSON.stringify(body) });
const patch = <T>(token: string | null, path: string, body: unknown) =>
  request<T>(token, path, { method: "PATCH", body: JSON.stringify(body) });
const del = (token: string | null, path: string) =>
  request<void>(token, path, { method: "DELETE" });

// -- me ---------------------------------------------------------------------

export const getMe = (token: string) => get<Me>(token, "/me");

// -- organizations -----------------------------------------------------------

export const listOrganizations = (token: string) =>
  get<Organization[]>(token, "/organizations");

export const createOrganization = (token: string, name: string) =>
  post<Organization>(token, "/organizations", { name });

export const listMembers = (token: string, orgId: string) =>
  get<Member[]>(token, `/organizations/${orgId}/members`);

// -- invitations --------------------------------------------------------------

export const inviteMember = (
  token: string,
  orgId: string,
  input: {
    email: string;
    scope: Invitation["scope"];
    role: string;
    team_id?: string;
    project_id?: string;
  },
) => post<Invitation>(token, `/organizations/${orgId}/invitations`, input);

/** Public: preview needs no bearer (token in the URL is the credential). */
export const previewInvitation = (tokenValue: string) =>
  get<InvitationPreview>(null, `/invitations/${tokenValue}`);

export const acceptInvitation = (token: string, tokenValue: string) =>
  post<void>(token, "/invitations/accept", { token: tokenValue });

// -- teams --------------------------------------------------------------------

export const listTeams = (token: string, orgId: string) =>
  get<Team[]>(token, `/organizations/${orgId}/teams`);

export const createTeam = (token: string, orgId: string, name: string) =>
  post<Team>(token, `/organizations/${orgId}/teams`, { name });

export const listTeamMembers = (token: string, teamId: string) =>
  get<TeamMember[]>(token, `/teams/${teamId}/members`);

// -- projects -----------------------------------------------------------------

export const listProjects = (token: string, orgId: string) =>
  get<Project[]>(token, `/organizations/${orgId}/projects`);

export const getProject = (token: string, projectId: string) =>
  get<Project>(token, `/projects/${projectId}`);

export const createProject = (
  token: string,
  orgId: string,
  input: { name: string; owning_team_id?: string | null; visibility: string },
) => post<Project>(token, `/organizations/${orgId}/projects`, input);

export const listProjectMembers = (token: string, projectId: string) =>
  get<ProjectMember[]>(token, `/projects/${projectId}/members`);

// -- project tags ---------------------------------------------------------------

export const listTags = (token: string, projectId: string) =>
  get<ProjectTag[]>(token, `/projects/${projectId}/tags`);

export const createTag = (
  token: string,
  projectId: string,
  input: { name: string; color?: string | null },
) => post<ProjectTag>(token, `/projects/${projectId}/tags`, input);

export const updateTag = (
  token: string,
  projectId: string,
  tagId: string,
  input: { name?: string; color?: string | null },
) => patch<ProjectTag>(token, `/projects/${projectId}/tags/${tagId}`, input);

export const deleteTag = (token: string, projectId: string, tagId: string) =>
  del(token, `/projects/${projectId}/tags/${tagId}`);

// -- research: notebooks ------------------------------------------------------

export const listNotebooks = (token: string, projectId: string) =>
  get<Notebook[]>(token, `/projects/${projectId}/notebooks`);

export const createNotebook = (
  token: string,
  projectId: string,
  input: { name: string; description?: string | null },
) => post<Notebook>(token, `/projects/${projectId}/notebooks`, input);

export const updateNotebook = (
  token: string,
  projectId: string,
  notebookId: string,
  input: { name?: string; description?: string | null; archived?: boolean },
) => patch<Notebook>(token, `/projects/${projectId}/notebooks/${notebookId}`, input);

export const deleteNotebook = (token: string, projectId: string, notebookId: string) =>
  del(token, `/projects/${projectId}/notebooks/${notebookId}`);

// -- research: sources ----------------------------------------------------------

export const listSources = (token: string, projectId: string) =>
  get<Source[]>(token, `/projects/${projectId}/sources`);

export const createSource = (
  token: string,
  projectId: string,
  input: { notebook_id: string; title: string; content: string },
) => post<Source>(token, `/projects/${projectId}/sources`, input);

export const retrySource = (token: string, projectId: string, sourceId: string) =>
  post<Source>(token, `/projects/${projectId}/sources/${sourceId}/retry`, {});

// -- research: search -----------------------------------------------------------

export const searchText = (token: string, projectId: string, q: string) =>
  get<SearchHit[]>(token, `/projects/${projectId}/search/text?q=${encodeURIComponent(q)}`);

export const searchVector = (token: string, projectId: string, q: string) =>
  get<SearchHit[]>(token, `/projects/${projectId}/search/vector?q=${encodeURIComponent(q)}`);

// -- research: notes --------------------------------------------------------------

export const listNotes = (token: string, projectId: string, notebookId: string) =>
  get<Note[]>(token, `/projects/${projectId}/notebooks/${notebookId}/notes`);

export const createNote = (
  token: string,
  projectId: string,
  notebookId: string,
  input: { title: string; content?: string },
) => post<Note>(token, `/projects/${projectId}/notebooks/${notebookId}/notes`, input);

export const updateNote = (
  token: string,
  projectId: string,
  notebookId: string,
  noteId: string,
  input: { title?: string; content?: string },
) => patch<Note>(token, `/projects/${projectId}/notebooks/${notebookId}/notes/${noteId}`, input);

export const deleteNote = (
  token: string,
  projectId: string,
  notebookId: string,
  noteId: string,
) => del(token, `/projects/${projectId}/notebooks/${notebookId}/notes/${noteId}`);

// -- competitors: directory -----------------------------------------------------

export const listCompetitors = (token: string, projectId: string) =>
  get<Competitor[]>(token, `/projects/${projectId}/competitors`);

export const createCompetitor = (
  token: string,
  projectId: string,
  input: { name: string; website?: string | null; notes?: string | null },
) => post<Competitor>(token, `/projects/${projectId}/competitors`, input);

export const updateCompetitor = (
  token: string,
  projectId: string,
  competitorId: string,
  input: { name?: string; website?: string | null; notes?: string | null },
) => patch<Competitor>(token, `/projects/${projectId}/competitors/${competitorId}`, input);

export const deleteCompetitor = (token: string, projectId: string, competitorId: string) =>
  del(token, `/projects/${projectId}/competitors/${competitorId}`);

export const listLocations = (token: string, projectId: string, competitorId: string) =>
  get<Location[]>(token, `/projects/${projectId}/competitors/${competitorId}/locations`);

export const createLocation = (
  token: string,
  projectId: string,
  competitorId: string,
  input: { name: string; address?: string | null },
) => post<Location>(token, `/projects/${projectId}/competitors/${competitorId}/locations`, input);

export const deleteLocation = (
  token: string,
  projectId: string,
  competitorId: string,
  locationId: string,
) => del(token, `/projects/${projectId}/competitors/${competitorId}/locations/${locationId}`);

// -- competitors: service catalog -------------------------------------------------

export const listServices = (token: string, projectId: string) =>
  get<Service[]>(token, `/projects/${projectId}/services`);

export const createService = (token: string, projectId: string, input: { name: string }) =>
  post<Service>(token, `/projects/${projectId}/services`, input);

export const deleteService = (token: string, projectId: string, serviceId: string) =>
  del(token, `/projects/${projectId}/services/${serviceId}`);

// -- competitors: observations + review queue --------------------------------------

export const listObservations = (token: string, projectId: string, competitorId: string) =>
  get<Observation[]>(token, `/projects/${projectId}/competitors/${competitorId}/observations`);

export const createObservation = (
  token: string,
  projectId: string,
  competitorId: string,
  input: {
    service_id?: string | null;
    location_id?: string | null;
    kind?: string;
    price_amount: string;
    price_currency: string;
    observed_on: string;
  },
) => post<Observation>(token, `/projects/${projectId}/competitors/${competitorId}/observations`, input);

export const reviewQueue = (token: string, projectId: string) =>
  get<Observation[]>(token, `/projects/${projectId}/review-queue`);

export const approveObservation = (token: string, projectId: string, observationId: string) =>
  post<Observation>(token, `/projects/${projectId}/observations/${observationId}/approve`, {});

export const rejectObservation = (token: string, projectId: string, observationId: string) =>
  post<Observation>(token, `/projects/${projectId}/observations/${observationId}/reject`, {});

// -- competitors: evidence ----------------------------------------------------------

export const listEvidence = (
  token: string,
  projectId: string,
  competitorId: string,
  filters: { target_kind?: string; observation_id?: string } = {},
) => {
  const params = new URLSearchParams();
  if (filters.target_kind) params.set("target_kind", filters.target_kind);
  if (filters.observation_id) params.set("observation_id", filters.observation_id);
  const qs = params.toString();
  return get<EvidenceLink[]>(
    token,
    `/projects/${projectId}/competitors/${competitorId}/evidence${qs ? `?${qs}` : ""}`,
  );
};

export const addEvidence = (
  token: string,
  projectId: string,
  competitorId: string,
  input: {
    target_kind: "source" | "notebook";
    target_id: string;
    observation_id?: string | null;
    excerpt?: string | null;
    excerpt_start?: number | null;
    excerpt_end?: number | null;
  },
) => post<EvidenceLink>(token, `/projects/${projectId}/competitors/${competitorId}/evidence`, input);

export const deleteEvidence = (
  token: string,
  projectId: string,
  competitorId: string,
  evidenceId: string,
) => del(token, `/projects/${projectId}/competitors/${competitorId}/evidence/${evidenceId}`);
