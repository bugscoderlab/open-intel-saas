"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { RequireAuth } from "@/components/layout/require-auth";
import { Card } from "@/components/ui/card";
import { listOrganizations, listProjects } from "@/lib/api/client";
import type { Organization, Project } from "@/lib/api/types";
import { useSession } from "@/lib/auth/use-session";

export default function ResearchModulePage() {
  return (
    <RequireAuth>
      <ResearchModule />
    </RequireAuth>
  );
}

/** Org-level entry: pick a project, then land in its research workspace. */
function ResearchModule() {
  const params = useParams<{ orgId: string }>();
  const orgId = params.orgId;
  const { session } = useSession();
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token) return;
    listOrganizations(session.access_token)
      .then(setOrgs)
      .catch(() => setOrgs([]));
    listProjects(session.access_token, orgId)
      .then(setProjects)
      .catch((cause) =>
        setError(cause instanceof Error ? cause.message : "Failed to load projects"),
      );
  }, [session?.access_token, orgId]);

  if (!session) return null;

  return (
    <AppShell email={session.user.email ?? ""} orgs={orgs} currentOrgId={orgId}>
      <Card>
        <h2 className="mb-1 text-base font-semibold text-gray-900">
          Research workspaces
        </h2>
        <p className="mb-4 text-sm text-gray-600">
          Notebooks, notes, source ingestion, and search live inside a project.
          Choose one:
        </p>
        {error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : projects.length === 0 ? (
          <p className="text-sm text-gray-600">
            No projects in this organization yet.
          </p>
        ) : (
          <ul className="space-y-2">
            {projects.map((project) => (
              <li key={project.id}>
                <Link
                  href={`/org/${orgId}/projects/${project.id}?view=notebooks`}
                  className="block rounded-lg border border-gray-200 px-4 py-3 text-sm font-medium text-blue-700 hover:bg-blue-50"
                >
                  {project.name} →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </AppShell>
  );
}
