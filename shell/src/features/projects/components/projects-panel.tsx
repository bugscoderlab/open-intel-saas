"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { createProject } from "@/lib/api/client";
import type { Project, Team } from "@/lib/api/types";

interface ProjectsPanelProps {
  accessToken: string;
  organizationId: string;
  projects: Project[];
  teams: Team[];
  onChanged: () => void;
}

/** Project management: org-owned or team-owned, with visibility
 *  (ticket #20). Any org member can create. */
export function ProjectsPanel({
  accessToken,
  organizationId,
  projects,
  teams,
  onChanged,
}: ProjectsPanelProps) {
  const [name, setName] = useState("");
  const [teamId, setTeamId] = useState("");
  const [visibility, setVisibility] = useState("private");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createProject(accessToken, organizationId, {
        name,
        owning_team_id: teamId || null,
        visibility,
      });
      setName("");
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to create project");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>Projects</CardTitle>
      <ul className="mb-4 divide-y divide-gray-100">
        {projects.map((project) => (
          <li key={project.id} className="flex items-center justify-between py-2">
            <Link
              href={`/org/${organizationId}/projects/${project.id}`}
              className="text-sm font-medium text-blue-700 hover:underline"
            >
              {project.name}
            </Link>
            <span className="flex gap-1">
              {project.owning_team_id ? (
                <Badge tone="blue">
                  team: {teams.find((team) => team.id === project.owning_team_id)?.name ?? "?"}
                </Badge>
              ) : (
                <Badge tone="gray">organization</Badge>
              )}
              <Badge tone="gray">{project.visibility}</Badge>
            </span>
          </li>
        ))}
        {projects.length === 0 ? (
          <li className="py-2 text-sm text-gray-500">No projects yet.</li>
        ) : null}
      </ul>
      <form onSubmit={submit} className="space-y-2">
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Field label="New project">
              <Input
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Competitor tracking"
              />
            </Field>
          </div>
          <div>
            <Field label="Owning team">
              <select
                className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
                value={teamId}
                onChange={(event) => setTeamId(event.target.value)}
              >
                <option value="">Organization-owned</option>
                {teams.map((team) => (
                  <option key={team.id} value={team.id}>
                    {team.name}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div>
            <Field label="Visibility">
              <select
                className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
                value={visibility}
                onChange={(event) => setVisibility(event.target.value)}
              >
                <option value="private">private</option>
                <option value="team">team</option>
                <option value="organization">organization</option>
              </select>
            </Field>
          </div>
          <Button type="submit" disabled={busy}>
            {busy ? "Creating…" : "Create project"}
          </Button>
        </div>
      </form>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
    </Card>
  );
}
