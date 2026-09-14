"use client";

import { useState } from "react";

import { createSource, retrySource } from "@/lib/api/client";
import type { Notebook, Source } from "@/lib/api/types";

import {
  btnSecondary,
  card,
  inputCls,
} from "@/components/workspace/bits";

const STATUS_STYLES: Record<string, string> = {
  ready: "bg-emerald-100 text-emerald-800",
  pending: "bg-amber-100 text-amber-800",
  processing: "bg-blue-100 text-blue-800",
  failed: "bg-red-100 text-red-700",
};

export function SourcesView({
  token,
  projectId,
  notebooks,
  sources,
  readOnly = false,
  onChanged,
}: {
  token: string;
  projectId: string;
  notebooks: Notebook[];
  sources: Source[];
  /** Viewers get no mutation controls (matrix mirror: source.create/retry
   *  are editor permissions). */
  readOnly?: boolean;
  onChanged: () => void;
}) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [notebookId, setNotebookId] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Request failed");
    }
  }

  return (
    <div className="space-y-4">
      {notebooks.length === 0 ? (
        <div className={`${card} text-sm text-[#737687]`}>
          Create a notebook first — sources are added inside a notebook.
        </div>
      ) : readOnly ? null : (
        <div className={`${card} space-y-2`}>
          <h3 className="text-sm font-semibold">Add a text source</h3>
          {error ? (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
          ) : null}
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              className={inputCls}
              placeholder="Source title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <select
              className={inputCls}
              value={notebookId}
              onChange={(e) => setNotebookId(e.target.value)}
            >
              <option value="">Choose a notebook…</option>
              {notebooks
                .filter((n) => !n.archived)
                .map((notebook) => (
                  <option key={notebook.id} value={notebook.id}>
                    {notebook.name}
                  </option>
                ))}
            </select>
          </div>
          <textarea
            className={`${inputCls} min-h-28`}
            placeholder="Paste the text content to ingest…"
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <button
            className={btnSecondary}
            disabled={!title.trim() || !content.trim() || !notebookId}
            onClick={async () => {
              await run(() =>
                createSource(token, projectId, {
                  notebook_id: notebookId,
                  title: title.trim(),
                  content: content.trim(),
                }),
              );
              setTitle("");
              setContent("");
            }}
          >
            Ingest source
          </button>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {sources.length === 0 ? (
          <div className={`${card} text-sm text-[#737687]`}>
            {readOnly
              ? "No sources yet."
              : "No sources yet — ingest one above. Processing runs asynchronously; watch the status flip to ready."}
          </div>
        ) : (
          sources.map((source) => (
            <div key={source.id} className={card}>
              <div className="mb-2 flex items-center justify-between">
                <span className="rounded bg-[#f0edff] px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-[#5a48c8]">
                  {source.type}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS_STYLES[source.status] ?? "bg-gray-100 text-gray-600"}`}
                >
                  {source.status}
                </span>
              </div>
              <h3 className="mb-1 text-sm font-semibold">{source.title}</h3>
              <p className="mb-2 text-xs text-[#737687]">
                {notebooks.find((n) => n.id === source.notebook_id)?.name ??
                  "no notebook"}
              </p>
              {source.error ? (
                <p className="mb-2 text-xs text-red-600">{source.error}</p>
              ) : null}
              {source.status === "failed" && !readOnly && (
                <button
                  className={btnSecondary}
                  onClick={() => run(() => retrySource(token, projectId, source.id))}
                >
                  Retry
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
