"use client";

import { useState } from "react";

import { searchText, searchVector } from "@/lib/api/client";
import type { SearchHit } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import {
  btnPrimary,
  card,
  inputCls,
} from "@/components/workspace/bits";

type Mode = "text" | "vector";

export function SearchView({
  token,
  projectId,
}: {
  token: string;
  projectId: string;
}) {
  const [mode, setMode] = useState<Mode>("text");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const results =
        mode === "text"
          ? await searchText(token, projectId, query.trim())
          : await searchVector(token, projectId, query.trim());
      setHits(results);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Search failed");
      setHits(null);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className={card}>
        <div className="mb-3 flex items-center gap-1 rounded-lg bg-[#f6f7fb] p-1">
          {(["text", "vector"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium",
                mode === m
                  ? "bg-white text-[#5a48c8] shadow-sm"
                  : "text-[#737687] hover:text-[#20212a]",
              )}
            >
              {m === "text" ? "Text search" : "Vector search"}
            </button>
          ))}
          <span className="ml-auto pr-2 text-xs text-[#737687]">
            {mode === "vector" ? "needs embeddings configured" : "keyword match"}
          </span>
        </div>
        <div className="flex gap-2">
          <input
            className={inputCls}
            placeholder={
              mode === "text"
                ? "Search project sources by keyword…"
                : "Ask semantically (e.g. how do competitors price grooming)…"
            }
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") search();
            }}
          />
          <button className={btnPrimary} disabled={searching} onClick={search}>
            {searching ? "Searching…" : "Search"}
          </button>
        </div>
        {error ? (
          <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        ) : null}
      </div>

      {hits !== null && (
        <div className="space-y-2">
          <p className="text-xs text-[#737687]">
            {hits.length} result{hits.length === 1 ? "" : "s"} · this project only
          </p>
          {hits.map((hit, i) => (
            <div key={`${hit.source_id}-${i}`} className={card}>
              <div className="mb-1 flex items-baseline justify-between gap-2">
                <h3 className="text-sm font-semibold">{hit.title}</h3>
                <span className="shrink-0 text-xs text-[#737687]">
                  score {hit.score.toFixed(3)}
                </span>
              </div>
              <p className="text-sm text-[#737687]">{hit.snippet}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
