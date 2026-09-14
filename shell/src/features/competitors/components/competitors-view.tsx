"use client";

import { useMemo, useState } from "react";

import { createCompetitor, deleteCompetitor } from "@/lib/api/client";
import type {
  Competitor,
  EvidenceLink,
  Location,
  Observation,
  Service,
} from "@/lib/api/types";

import {
  btnPrimary,
  btnSecondary,
  card,
  inputCls,
  Logo,
} from "@/components/workspace/bits";
import { CompetitorDetail } from "./competitor-detail";

interface CompetitorsViewProps {
  token: string;
  projectId: string;
  competitors: Competitor[];
  locationsByCompetitor: Record<string, Location[]>;
  observationsByCompetitor: Record<string, Observation[]>;
  evidenceByCompetitor: Record<string, EvidenceLink[]>;
  services: Service[];
  readOnly: boolean;
  onChanged: () => void;
}

export function CompetitorsView({
  token,
  projectId,
  competitors,
  locationsByCompetitor,
  observationsByCompetitor,
  evidenceByCompetitor,
  services,
  readOnly,
  onChanged,
}: CompetitorsViewProps) {
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return competitors;
    return competitors.filter((c) => c.name.toLowerCase().includes(q));
  }, [competitors, query]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <input
          className={`${inputCls} max-w-xs`}
          placeholder="Search competitors"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="ml-auto" />
        {!readOnly && (
          <button className={btnPrimary} onClick={() => setAdding((v) => !v)}>
            ＋ Add competitor
          </button>
        )}
      </div>

      {error ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      ) : null}

      {adding && !readOnly ? (
        <AddCompetitorForm
          onCancel={() => setAdding(false)}
          onSubmit={async (input) => {
            setError(null);
            try {
              await createCompetitor(token, projectId, input);
              setAdding(false);
              onChanged();
            } catch (cause) {
              setError(cause instanceof Error ? cause.message : "Create failed");
            }
          }}
        />
      ) : null}

      <div className={`${card} overflow-hidden p-0`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#e7e8ef] text-left text-xs uppercase tracking-wide text-[#737687]">
              <th className="px-5 py-3 font-semibold">Competitor</th>
              <th className="px-3 py-3 font-semibold">Branches</th>
              <th className="px-3 py-3 font-semibold">Observations</th>
              <th className="px-3 py-3 font-semibold">Price range</th>
              <th className="px-3 py-3 font-semibold">Last activity</th>
              <th className="px-3 py-3" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-[#737687]">
                  {competitors.length === 0
                    ? "No competitors yet — add your first one."
                    : "No competitors match the search."}
                </td>
              </tr>
            ) : (
              filtered.map((competitor) => {
                const observations = observationsByCompetitor[competitor.id] ?? [];
                const approved = observations.filter(
                  (o) => o.approval_state === "approved" && o.price_amount,
                );
                const prices = approved.map((o) => Number(o.price_amount));
                const range =
                  prices.length === 0
                    ? "—"
                    : `${competitorCurrency(approved)} ${Math.min(...prices)}–${Math.max(...prices)}`;
                const last = observations
                  .map((o) => o.observed_on)
                  .sort()
                  .at(-1);
                return (
                  <CompetitorRow
                    key={competitor.id}
                    competitor={competitor}
                    branchCount={(locationsByCompetitor[competitor.id] ?? []).length}
                    observationCount={observations.length}
                    priceRange={range}
                    lastActivity={last ?? "—"}
                    open={expanded === competitor.id}
                    readOnly={readOnly}
                    onToggle={() =>
                      setExpanded((cur) =>
                        cur === competitor.id ? null : competitor.id,
                      )
                    }
                    onDelete={async () => {
                      setError(null);
                      try {
                        await deleteCompetitor(token, projectId, competitor.id);
                        onChanged();
                      } catch (cause) {
                        setError(
                          cause instanceof Error ? cause.message : "Delete failed",
                        );
                      }
                    }}
                    detail={
                      expanded === competitor.id ? (
                        <CompetitorDetail
                          token={token}
                          projectId={projectId}
                          competitor={competitor}
                          locations={locationsByCompetitor[competitor.id] ?? []}
                          services={services}
                          observations={observations}
                          evidence={evidenceByCompetitor[competitor.id] ?? []}
                          readOnly={readOnly}
                          onChanged={onChanged}
                        />
                      ) : null
                    }
                  />
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CompetitorRow({
  competitor,
  branchCount,
  observationCount,
  priceRange,
  lastActivity,
  open,
  readOnly,
  onToggle,
  onDelete,
  detail,
}: {
  competitor: Competitor;
  branchCount: number;
  observationCount: number;
  priceRange: string;
  lastActivity: string;
  open: boolean;
  readOnly: boolean;
  onToggle: () => void;
  onDelete: () => void;
  detail: React.ReactNode;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer border-b border-[#e7e8ef] last:border-0 hover:bg-[#f6f7fb]"
      >
        <td className="px-5 py-3">
          <span className="flex items-center gap-2.5 font-medium">
            <Logo name={competitor.name} />
            {competitor.name}
          </span>
        </td>
        <td className="px-3 py-3">{branchCount}</td>
        <td className="px-3 py-3">{observationCount}</td>
        <td className="px-3 py-3">{priceRange}</td>
        <td className="px-3 py-3 text-[#737687]">{lastActivity}</td>
        <td className="px-3 py-3 text-right">
          {!readOnly && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              className="text-xs text-red-600 hover:underline"
            >
              delete
            </button>
          )}
        </td>
      </tr>
      {open ? (
        <tr>
          <td colSpan={6} className="bg-[#fafafe]">
            {detail}
          </td>
        </tr>
      ) : null}
    </>
  );
}

function AddCompetitorForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (input: {
    name: string;
    website: string | null;
    notes: string | null;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [notes, setNotes] = useState("");
  return (
    <div className={`${card} space-y-2`}>
      <div className="grid gap-2 sm:grid-cols-2">
        <input
          className={inputCls}
          placeholder="Name (e.g. Paw Spa)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className={inputCls}
          placeholder="Website (optional)"
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
        />
      </div>
      <input
        className={inputCls}
        placeholder="Notes (optional)"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      <div className="flex gap-2">
        <button
          className={btnPrimary}
          disabled={!name.trim()}
          onClick={() =>
            onSubmit({
              name: name.trim(),
              website: website.trim() || null,
              notes: notes.trim() || null,
            })
          }
        >
          Create competitor
        </button>
        <button className={btnSecondary} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function competitorCurrency(observations: Observation[]): string {
  return observations[0]?.price_currency ?? "";
}
