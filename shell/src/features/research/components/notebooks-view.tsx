"use client";

import { useState } from "react";

import {
  createNote,
  createNotebook,
  deleteNote,
  deleteNotebook,
  updateNote,
  updateNotebook,
} from "@/lib/api/client";
import type { Note, Notebook, Source } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import {
  btnPrimary,
  btnSecondary,
  card,
  inputCls,
} from "@/components/workspace/bits";

interface NotebooksViewProps {
  token: string;
  projectId: string;
  notebooks: Notebook[];
  notesByNotebook: Record<string, Note[]>;
  /** Project sources; filtered to the active notebook for its detail. */
  sources: Source[];
  activeNotebookId: string | null;
  readOnly: boolean;
  onSelectNotebook: (id: string | null) => void;
  onChanged: () => void;
}

export function NotebooksView({
  token,
  projectId,
  notebooks,
  notesByNotebook,
  sources,
  activeNotebookId,
  readOnly,
  onSelectNotebook,
  onChanged,
}: NotebooksViewProps) {
  const [creating, setCreating] = useState(false);
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

  const active = notebooks.find((n) => n.id === activeNotebookId) ?? null;
  const notes = activeNotebookId ? (notesByNotebook[activeNotebookId] ?? []) : [];

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section className={card}>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Notebooks</h3>
          {!readOnly && (
            <button className={btnSecondary} onClick={() => setCreating((v) => !v)}>
              ＋ New
            </button>
          )}
        </div>
        {error ? (
          <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        ) : null}
        {creating && !readOnly ? (
          <NewNotebookForm
            onCancel={() => setCreating(false)}
            onSubmit={async (input) => {
              await run(() => createNotebook(token, projectId, input));
              setCreating(false);
            }}
          />
        ) : null}
        <ul className="space-y-1">
          {notebooks.length === 0 ? (
            <li className="text-sm text-[#737687]">No notebooks yet.</li>
          ) : (
            notebooks.map((notebook) => (
              <li key={notebook.id} className="flex items-center gap-1">
                <button
                  onClick={() => onSelectNotebook(notebook.id)}
                  className={cn(
                    "min-w-0 flex-1 truncate rounded-lg px-3 py-2 text-left text-sm",
                    notebook.id === activeNotebookId
                      ? "bg-[#f0edff] font-semibold text-[#5a48c8]"
                      : "hover:bg-[#f6f7fb]",
                  )}
                >
                  {notebook.name}
                  {notebook.archived ? (
                    <span className="ml-1 text-xs text-[#737687]">(archived)</span>
                  ) : null}
                </button>
                {!readOnly && (
                  <span className="flex shrink-0 gap-1 text-xs">
                    <button
                      className="text-[#737687] hover:underline"
                      onClick={() =>
                        run(() =>
                          updateNotebook(token, projectId, notebook.id, {
                            archived: !notebook.archived,
                          }),
                        )
                      }
                    >
                      {notebook.archived ? "restore" : "archive"}
                    </button>
                    <button
                      className="text-red-600 hover:underline"
                      onClick={() => {
                        if (notebook.id === activeNotebookId) onSelectNotebook(null);
                        run(() => deleteNotebook(token, projectId, notebook.id));
                      }}
                    >
                      delete
                    </button>
                  </span>
                )}
              </li>
            ))
          )}
        </ul>
      </section>

      {/* The chat column of the notebook detail arrives in Phase 7
          (intelligence chatbot) — it slots in beside these two columns
          (spec #36). */}
      {!active ? (
        <section className={`${card} lg:col-span-2`}>
          <h3 className="mb-3 text-sm font-semibold">Notebook detail</h3>
          <p className="text-sm text-[#737687]">
            Select a notebook to see its sources and notes side by side.
          </p>
        </section>
      ) : (
        <div className="grid gap-4 lg:col-span-2 lg:grid-cols-2">
          <section className={card}>
            <h3 className="mb-3 text-sm font-semibold">Sources — {active.name}</h3>
            <NotebookSources
              sources={sources.filter((s) => s.notebook_id === active.id)}
            />
          </section>
          <section className={card}>
            <h3 className="mb-3 text-sm font-semibold">Notes — {active.name}</h3>
            <NotesEditor
              token={token}
              projectId={projectId}
              notebookId={active.id}
              notes={notes}
              readOnly={readOnly}
              onChanged={onChanged}
            />
          </section>
        </div>
      )}
    </div>
  );
}

/** Sources of the open notebook (read-only here; ingestion and retry live
 *  in the workspace Sources view). */
function NotebookSources({ sources }: { sources: Source[] }) {
  if (sources.length === 0) {
    return <p className="text-sm text-[#737687]">No sources in this notebook.</p>;
  }
  return (
    <ul className="space-y-2">
      {sources.map((source) => (
        <li key={source.id} className="text-sm">
          <span className="mr-1.5 inline-block rounded bg-[#f0edff] px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-[#5a48c8]">
            {source.type}
          </span>
          <span className="font-medium">{source.title}</span>
          <span className="ml-1.5 text-xs text-[#737687]">{source.status}</span>
          {source.error ? (
            <p className="mt-0.5 text-xs text-red-600">{source.error}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function NewNotebookForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (input: { name: string; description?: string | null }) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  return (
    <div className="mb-3 space-y-2">
      <input
        className={inputCls}
        placeholder="Notebook name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <input
        className={inputCls}
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className="flex gap-2">
        <button
          className={btnPrimary}
          disabled={!name.trim()}
          onClick={() =>
            onSubmit({ name: name.trim(), description: description.trim() || null })
          }
        >
          Create notebook
        </button>
        <button className={btnSecondary} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function NotesEditor({
  token,
  projectId,
  notebookId,
  notes,
  readOnly,
  onChanged,
}: {
  token: string;
  projectId: string;
  notebookId: string;
  notes: Note[];
  readOnly: boolean;
  onChanged: () => void;
}) {
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
    <div className="space-y-3">
      {error ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      ) : null}
      {notes.length === 0 ? (
        <p className="text-sm text-[#737687]">This notebook has no notes yet.</p>
      ) : (
        notes.map((note) => (
          <NoteCard
            key={note.id}
            note={note}
            readOnly={readOnly}
            onSave={(input) =>
              run(() => updateNote(token, projectId, notebookId, note.id, input))
            }
            onDelete={() => run(() => deleteNote(token, projectId, notebookId, note.id))}
          />
        ))
      )}
      {!readOnly && (
        <NewNoteForm
          onSubmit={async (input) => {
            await run(() => createNote(token, projectId, notebookId, input));
          }}
        />
      )}
    </div>
  );
}

function NoteCard({
  note,
  readOnly,
  onSave,
  onDelete,
}: {
  note: Note;
  readOnly: boolean;
  onSave: (input: { title: string; content: string }) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(note.title);
  const [content, setContent] = useState(note.content);

  return (
    <div className="rounded-xl border border-[#e7e8ef] p-3">
      {editing ? (
        <div className="space-y-2">
          <input
            className={inputCls}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            className={`${inputCls} min-h-24`}
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              className={btnSecondary}
              onClick={() => {
                onSave({ title: title.trim(), content });
                setEditing(false);
              }}
            >
              Save
            </button>
            <button className={btnSecondary} onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-baseline justify-between gap-2">
            <h4 className="text-sm font-semibold">{note.title}</h4>
            {!readOnly && (
              <span className="flex shrink-0 gap-2 text-xs">
                <button
                  className="text-[#737687] hover:underline"
                  onClick={() => setEditing(true)}
                >
                  edit
                </button>
                <button className="text-red-600 hover:underline" onClick={onDelete}>
                  delete
                </button>
              </span>
            )}
          </div>
          {note.content ? (
            <p className="mt-1 whitespace-pre-wrap text-sm text-[#737687]">
              {note.content}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}

function NewNoteForm({
  onSubmit,
}: {
  onSubmit: (input: { title: string; content: string }) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  return (
    <div className="space-y-2 rounded-xl border border-dashed border-[#d8d9e4] p-3">
      <input
        className={inputCls}
        placeholder="Note title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <textarea
        className={`${inputCls} min-h-20`}
        placeholder="Note content (optional)"
        value={content}
        onChange={(e) => setContent(e.target.value)}
      />
      <button
        className={btnSecondary}
        disabled={!title.trim()}
        onClick={async () => {
          await onSubmit({ title: title.trim(), content });
          setTitle("");
          setContent("");
        }}
      >
        Add note
      </button>
    </div>
  );
}
