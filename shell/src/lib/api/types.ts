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

// -- research module (Phase 2) ------------------------------------------------

export interface Notebook {
  id: string;
  organization_id: string;
  project_id: string;
  name: string;
  description: string | null;
  archived: boolean;
}

export interface Source {
  id: string;
  organization_id: string;
  project_id: string;
  notebook_id: string | null;
  title: string;
  type: string;
  status: string;
  error: string | null;
}

export interface SearchHit {
  source_id: string;
  title: string;
  snippet: string;
  score: number;
}

export interface Note {
  id: string;
  organization_id: string;
  project_id: string;
  notebook_id: string;
  title: string;
  content: string;
}

// -- competitor intelligence module (Phase 3) ---------------------------------

export interface Competitor {
  id: string;
  organization_id: string;
  project_id: string;
  name: string;
  website: string | null;
  notes: string | null;
}

export interface Location {
  id: string;
  organization_id: string;
  project_id: string;
  competitor_id: string;
  name: string;
  address: string | null;
}

export interface Service {
  id: string;
  organization_id: string;
  project_id: string;
  name: string;
}

export interface Observation {
  id: string;
  organization_id: string;
  project_id: string;
  competitor_id: string;
  service_id: string | null;
  location_id: string | null;
  kind: string;
  price_amount: string | null;
  price_currency: string | null;
  observed_on: string;
  confidence: string;
  extraction_version: string;
  approval_state: "pending" | "approved" | "rejected" | "superseded" | string;
  superseded_by: string | null;
}

export interface EvidenceLink {
  id: string;
  organization_id: string;
  project_id: string;
  competitor_id: string;
  observation_id: string | null;
  target_kind: string;
  target_id: string;
  excerpt: string | null;
  excerpt_start: number | null;
  excerpt_end: number | null;
  approval_state: string;
}
