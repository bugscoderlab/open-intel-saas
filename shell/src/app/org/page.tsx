"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { RequireAuth } from "@/components/layout/require-auth";
import { Card, CardTitle } from "@/components/ui/card";
import { CreateOrgForm } from "@/features/organizations/components/create-org-form";
import { useSession } from "@/lib/auth/use-session";
import { listOrganizations } from "@/lib/api/client";
import type { Organization } from "@/lib/api/types";

export default function OrgPickerPage() {
  return (
    <RequireAuth>
      <OrgPicker />
    </RequireAuth>
  );
}

function OrgPicker() {
  const { accessToken } = useSession();
  const [orgs, setOrgs] = useState<Organization[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      setOrgs(await listOrganizations(accessToken));
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load");
    }
  }, [accessToken]);

  useEffect(() => {
    load();
  }, [load]);

  if (!accessToken) return null;

  return (
    <main className="mx-auto max-w-md space-y-4 px-4 py-12">
      <h1 className="text-xl font-bold text-gray-900">Your organizations</h1>
      {error ? (
        <Card>
          <p className="text-sm text-red-600">
            Could not reach the backend ({error}). Is the API running on port
            5055?
          </p>
        </Card>
      ) : null}
      <Card>
        <CardTitle>Organizations</CardTitle>
        {orgs === null ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : orgs.length === 0 ? (
          <p className="text-sm text-gray-500">
            You are not a member of any organization yet — create one below.
          </p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {orgs.map((org) => (
              <li key={org.id}>
                <Link
                  href={`/org/${org.id}`}
                  className="block py-2 text-sm font-medium text-blue-700 hover:underline"
                >
                  {org.name}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <CreateOrgForm accessToken={accessToken} />
    </main>
  );
}
