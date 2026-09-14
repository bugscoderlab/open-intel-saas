"use client";

import { useState } from "react";

import { approveObservation, rejectObservation } from "@/lib/api/client";
import type { Competitor, Observation, Service } from "@/lib/api/types";

import { btnSecondary, card, formatPrice, StateBadge } from "@/components/workspace/bits";

interface ReviewViewProps {
  token: string;
  projectId: string;
  queue: Observation[];
  competitors: Competitor[];
  services: Service[];
  readOnly: boolean;
  onChanged: () => void;
}

/** The review queue (glossary): pending observations awaiting a human
 *  decision. Approve/reject are the only transitions offered here. */
export function ReviewView({
  token,
  projectId,
  queue,
  competitors,
  services,
  readOnly,
  onChanged,
}: ReviewViewProps) {
  const [error, setError] = useState<string | null>(null);

  async function decide(observationId: string, decision: "approve" | "reject") {
    setError(null);
    try {
      if (decision === "approve") {
        await approveObservation(token, projectId, observationId);
      } else {
        await rejectObservation(token, projectId, observationId);
      }
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Decision failed");
    }
  }

  return (
    <div className="space-y-4">
      {error ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      ) : null}
      <div className={`${card} overflow-hidden p-0`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#e7e8ef] text-left text-xs uppercase tracking-wide text-[#737687]">
              <th className="px-5 py-3 font-semibold">Competitor</th>
              <th className="px-3 py-3 font-semibold">Service</th>
              <th className="px-3 py-3 font-semibold">Price</th>
              <th className="px-3 py-3 font-semibold">Observed</th>
              <th className="px-3 py-3 font-semibold">State</th>
              <th className="px-3 py-3" />
            </tr>
          </thead>
          <tbody>
            {queue.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-[#737687]">
                  Review queue is empty — new observations land here as pending.
                </td>
              </tr>
            ) : (
              queue.map((observation) => (
                <tr key={observation.id} className="border-b border-[#e7e8ef] last:border-0">
                  <td className="px-5 py-3 font-medium">
                    {competitors.find((c) => c.id === observation.competitor_id)?.name ??
                      "Unknown"}
                  </td>
                  <td className="px-3 py-3">
                    {services.find((s) => s.id === observation.service_id)?.name ??
                      "market level"}
                  </td>
                  <td className="px-3 py-3">{formatPrice(observation)}</td>
                  <td className="px-3 py-3 text-[#737687]">{observation.observed_on}</td>
                  <td className="px-3 py-3">
                    <StateBadge state={observation.approval_state} />
                  </td>
                  <td className="px-3 py-3 text-right">
                    {!readOnly && (
                      <span className="flex justify-end gap-2">
                        <button
                          className={btnSecondary}
                          onClick={() => decide(observation.id, "approve")}
                        >
                          Approve
                        </button>
                        <button
                          className="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
                          onClick={() => decide(observation.id, "reject")}
                        >
                          Reject
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-[#737687]">
        Approving a different price for the same service supersedes the current
        approved value and records a Change; an identical value is not a Change.
        Rejected rows are kept for audit.
      </p>
    </div>
  );
}
