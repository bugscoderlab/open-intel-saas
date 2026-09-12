"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, createTag, deleteTag, updateTag } from "@/lib/api/client";
import type { ProjectTag } from "@/lib/api/types";

interface TagsPanelProps {
  accessToken: string;
  projectId: string;
  tags: ProjectTag[];
  /** False for viewers: read-only listing, no controls rendered. */
  canEdit: boolean;
  onChanged: () => void;
}

/** Project tag CRUD for editors; read-only listing for viewers
 *  (ticket #20). */
export function TagsPanel({
  accessToken,
  projectId,
  tags,
  canEdit,
  onChanged,
}: TagsPanelProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createTag(accessToken, projectId, { name });
      setName("");
      onChanged();
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 403
          ? "Viewers cannot add tags."
          : cause instanceof Error
            ? cause.message
            : "Failed to add tag",
      );
    } finally {
      setBusy(false);
    }
  }

  async function rename(tag: ProjectTag) {
    const next = window.prompt("Rename tag", tag.name);
    if (!next || next === tag.name) return;
    try {
      await updateTag(accessToken, projectId, tag.id, { name: next });
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to rename");
    }
  }

  async function remove(tag: ProjectTag) {
    if (!window.confirm(`Delete tag "${tag.name}"?`)) return;
    try {
      await deleteTag(accessToken, projectId, tag.id);
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to delete");
    }
  }

  return (
    <div>
      <ul className="mb-3 flex flex-wrap gap-2">
        {tags.map((tag) => (
          <li
            key={tag.id}
            className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800"
          >
            {tag.name}
            {canEdit ? (
              <span className="flex gap-1 text-xs">
                <button
                  type="button"
                  className="text-blue-600 hover:underline"
                  onClick={() => rename(tag)}
                >
                  rename
                </button>
                <button
                  type="button"
                  className="text-red-600 hover:underline"
                  onClick={() => remove(tag)}
                >
                  delete
                </button>
              </span>
            ) : null}
          </li>
        ))}
        {tags.length === 0 ? (
          <li className="text-sm text-gray-500">No tags yet.</li>
        ) : null}
      </ul>
      {canEdit ? (
        <form onSubmit={submit} className="flex items-center gap-2">
          <input
            className="w-56 rounded-md border border-gray-300 px-3 py-1.5 text-sm"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="New tag"
          />
          <Button type="submit" disabled={busy}>
            {busy ? "Adding…" : "Add tag"}
          </Button>
        </form>
      ) : (
        <p className="text-xs text-gray-500">You have viewer access: tags are read-only.</p>
      )}
      {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}
    </div>
  );
}
