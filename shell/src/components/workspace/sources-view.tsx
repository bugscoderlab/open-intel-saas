"use client";

import { useState } from "react";

import {
  addEvidence,
  createSource,
  deleteEvidence,
  retrySource,
} from "@/lib/api/client";
import type {
  Competitor,
  EvidenceLink,
  Notebook,
  Source,
} from "@/lib/api/types";

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
  competitors,
  evidenceByCompetitor,
  readOnly = false,
  onChanged,
}: {
  token: string;
  projectId: string;
  notebooks: Notebook[];
  sources: Source[];
  /** Competitors + their evidence links: a source is evidence when a
   *  competitor's evidence list targets it (PDR-004 — sources are shared
   *  by research and competitor intelligence). */
  competitors: Competitor[];
  evidenceByCompetitor: Record<string, EvidenceLink[]>;
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

  /** Every competitor this source is attached to as evidence. */
  function evidenceFor(sourceId: string) {
    return competitors.flatMap((competitor) =>
      (evidenceByCompetitor[competitor.id] ?? [])
        .filter((link) => link.target_kind === "source" && link.target_id === sourceId)
        .map((link) => ({ competitor, link })),
    );
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
              <SourceEvidence
                token={token}
                projectId={projectId}
                sourceId={source.id}
                competitors={competitors}
                evidence={evidenceFor(source.id)}
                readOnly={readOnly}
                onChanged={onChanged}
              />
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/** Evidence links for one source: which competitors cite it, and (for
 *  editors) a form to attach it to a competitor. */
function SourceEvidence({
  token,
  projectId,
  sourceId,
  competitors,
  evidence,
  readOnly,
  onChanged,
}: {
  token: string;
  projectId: string;
  sourceId: string;
  competitors: Competitor[];
  evidence: { competitor: Competitor; link: EvidenceLink }[];
  readOnly: boolean;
  onChanged: () => void;
}) {
  const [competitorId, setCompetitorId] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function link() {
    setError(null);
    try {
      await addEvidence(token, projectId, competitorId, {
        target_kind: "source",
        target_id: sourceId,
        excerpt: excerpt.trim() || null,
      });
      setCompetitorId("");
      setExcerpt("");
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Request failed");
    }
  }

  async function unlink(competitorId: string, evidenceId: string) {
    setError(null);
    try {
      await deleteEvidence(token, projectId, competitorId, evidenceId);
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Request failed");
    }
  }

  return (
    <div className="mt-3 border-t border-[#e7e8ef] pt-3">
      <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[#9496a4]">
        Evidence for
      </div>
      {evidence.length === 0 ? (
        <p className="text-xs text-[#737687]">Not cited by any competitor yet.</p>
      ) : (
        <ul className="mb-2 space-y-1">
          {evidence.map(({ competitor, link }) => (
            <li key={link.id} className="flex items-center gap-2 text-xs">
              <span className="rounded bg-[#f0edff] px-1.5 py-0.5 font-semibold text-[#5a48c8]">
                {competitor.name}
              </span>
              {link.excerpt ? (
                <span className="min-w-0 flex-1 truncate text-[#737687]">
                  “{link.excerpt}”
                </span>
              ) : (
                <span className="flex-1" />
              )}
              {!readOnly && (
                <button
                  onClick={() => unlink(competitor.id, link.id)}
                  className="text-red-600 hover:underline"
                >
                  remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {error ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>
      ) : null}
      {!readOnly &&
        (competitors.length === 0 ? (
          <p className="text-xs text-[#737687]">
            Add a competitor first to cite this source as evidence.
          </p>
        ) : (
          <div className="space-y-1.5">
            <div className="flex gap-1.5">
              <select
                className={inputCls}
                value={competitorId}
                onChange={(e) => setCompetitorId(e.target.value)}
              >
                <option value="">Cite as evidence for…</option>
                {competitors.map((competitor) => (
                  <option key={competitor.id} value={competitor.id}>
                    {competitor.name}
                  </option>
                ))}
              </select>
              <button
                className={`${btnSecondary} shrink-0`}
                disabled={!competitorId}
                onClick={link}
              >
                Link
              </button>
            </div>
            <input
              className={inputCls}
              placeholder="Excerpt (optional)"
              value={excerpt}
              onChange={(e) => setExcerpt(e.target.value)}
            />
          </div>
        ))}
    </div>
  );
}
