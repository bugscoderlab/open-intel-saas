"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { createOrganization } from "@/lib/api/client";

/** Organization creation — any authenticated user (ticket #19). */
export function CreateOrgForm({ accessToken }: { accessToken: string }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const organization = await createOrganization(accessToken, name);
      router.push(`/org/${organization.id}`);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to create");
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardTitle>Create an organization</CardTitle>
      <form onSubmit={submit} className="flex items-end gap-2">
        <div className="flex-1">
          <Field label="Name">
            <Input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Acme Intelligence"
            />
          </Field>
        </div>
        <Button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create"}
        </Button>
      </form>
      {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}
    </Card>
  );
}
