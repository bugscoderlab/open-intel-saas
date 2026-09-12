/** Response shapes mirror modules/platform/api/schemas.py (ticket #19). */

export interface Me {
  app_user_id: string;
  email: string;
  email_confirmed: boolean;
}

export interface Organization {
  id: string;
  name: string;
}

export type OrgRole = "owner" | "admin" | "member";

export interface Member {
  app_user_id: string;
  role: OrgRole;
  email: string | null;
}

export type InvitationScope = "organization" | "team" | "project";

export interface Invitation {
  id: string;
  organization_id: string;
  scope: InvitationScope;
  team_id: string | null;
  project_id: string | null;
  email: string;
  role: string;
  expires_at: string;
}

export interface InvitationPreview {
  email: string;
  scope: InvitationScope;
  role: string;
  organization_name: string;
  expires_at: string;
}

export interface Team {
  id: string;
  organization_id: string;
  name: string;
}

export type TeamRole = "manager" | "member";

export interface TeamMember {
  team_id: string;
  app_user_id: string;
  role: TeamRole;
}

export type Visibility = "private" | "team" | "organization";

export interface Project {
  id: string;
  organization_id: string;
  owning_team_id: string | null;
  name: string;
  visibility: Visibility;
}

export type ProjectRole = "editor" | "viewer";

export interface ProjectMember {
  project_id: string;
  app_user_id: string;
  role: ProjectRole;
}

export interface ProjectTag {
  id: string;
  organization_id: string;
  project_id: string;
  name: string;
  color: string | null;
}
