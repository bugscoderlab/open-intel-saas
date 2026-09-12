import { env } from "@/lib/env";
import type {
  Invitation,
  InvitationPreview,
  Me,
  Member,
  Organization,
  Project,
  ProjectMember,
  ProjectTag,
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
