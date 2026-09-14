"use client";

import { useState } from "react";

import { createService, deleteService } from "@/lib/api/client";
import type {
  Competitor,
  EvidenceLink,
  Location,
  Observation,
  Service,
} from "@/lib/api/types";

import {
  btnSecondary,
  card,
  formatPrice,
  inputCls,
  Logo,
  StateBadge,
} from "@/components/workspace/bits";

interface OverviewViewProps {
  token: string;
  projectId: string;
  competitors: Competitor[];
  services: Service[];
  queue: Observation[];
  locationsByCompetitor: Record<string, Location[]>;
  observationsByCompetitor: Record<string, Observation[]>;
  evidenceByCompetitor: Record<string, EvidenceLink[]>;
  readOnly: boolean;
  onChanged: () => void;
}

export function OverviewView({
  token,
  projectId,
  competitors,
  services,
  queue,
  locationsByCompetitor,
  observationsByCompetitor,
  evidenceByCompetitor,
  readOnly,
  onChanged,
}: OverviewViewProps) {
  const allObservations = Object.values(observationsByCompetitor).flat();
  const approved = allObservations.filter((o) => o.approval_state === "approved");
  const approvedPrices = approved
    .filter((o) => o.price_amount)
    .map((o) => Number(o.price_amount))
    .sort((a, b) => a - b);
  const median =
    approvedPrices.length === 0
      ? null
      : approvedPrices.length % 2 === 1
        ? approvedPrices[(approvedPrices.length - 1) / 2]
        : (approvedPrices[approvedPrices.length / 2 - 1] +
            approvedPrices[approvedPrices.length / 2]) /
          2;
  const evidenceCount = Object.values(evidenceByCompetitor).flat().length;
  const branchCount = Object.values(locationsByCompetitor).flat().length;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Competitors tracked"
          value={String(competitors.length)}
          foot={`${branchCount} branches`}
        />
        <Metric
          label="Services in catalog"
          value={String(services.length)}
          foot="defined once per project"
        />
        <Metric
          label="Median approved price"
          value={median == null ? "—" : String(median)}
          foot={`${approved.length} approved observations`}
        />
        <Metric
          label="Needs your review"
          value={String(queue.length)}
          foot={`${evidenceCount} evidence links`}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <section className={`${card} xl:col-span-2`}>
          <div className="mb-3 flex items-baseline justify-between">
            <h3 className="text-sm font-semibold">Competitive position</h3>
            <span className="text-xs text-[#737687]">
              latest approved price per competitor
            </span>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#e7e8ef] text-left text-xs uppercase tracking-wide text-[#737687]">
                <th className="py-2 pr-3 font-semibold">Competitor</th>
                <th className="py-2 pr-3 font-semibold">Approved facts</th>
                <th className="py-2 pr-3 font-semibold">Latest price</th>
                <th className="py-2 font-semibold">Signals</th>
              </tr>
            </thead>
            <tbody>
              {competitors.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-[#737687]">
                    Add competitors to see the position table.
                  </td>
                </tr>
              ) : (
                competitors.map((competitor) => {
                  const rows = (observationsByCompetitor[competitor.id] ?? []).filter(
                    (o) => o.approval_state === "approved" && o.price_amount,
                  );
                  const latest = rows.at(-1);
                  const signalCount = (
                    observationsByCompetitor[competitor.id] ?? []
                  ).filter((o) => o.approval_state === "superseded").length;
                  return (
                    <tr
                      key={competitor.id}
                      className="border-b border-[#e7e8ef] last:border-0"
                    >
                      <td className="py-2.5 pr-3">
                        <span className="flex items-center gap-2">
                          <Logo name={competitor.name} />
                          {competitor.name}
                        </span>
                      </td>
                      <td className="py-2.5 pr-3">{rows.length}</td>
                      <td className="py-2.5 pr-3">
                        {latest ? formatPrice(latest) : "—"}
                      </td>
                      <td className="py-2.5">
                        {signalCount === 0 ? (
                          <span className="text-[#737687]">—</span>
                        ) : (
                          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                            {signalCount} change{signalCount === 1 ? "" : "s"}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </section>

        <section className={card}>
          <h3 className="mb-3 text-sm font-semibold">Latest intelligence</h3>
          <ul className="space-y-3">
            {allObservations.length === 0 ? (
              <li className="text-sm text-[#737687]">
                Observations and review decisions will appear here.
              </li>
            ) : (
              [...allObservations]
                .reverse()
                .slice(0, 8)
                .map((observation) => (
                  <li key={observation.id} className="text-sm">
                    <span className="mb-0.5 flex items-center gap-2">
                      <StateBadge state={observation.approval_state} />
                      <span className="text-xs text-[#737687]">
                        {observation.observed_on}
                      </span>
                    </span>
                    {competitors.find((c) => c.id === observation.competitor_id)
                      ?.name ?? "Unknown"}{" "}
                    — {formatPrice(observation)}
                  </li>
                ))
            )}
          </ul>
        </section>
      </div>

      <ServiceCatalog
        token={token}
        projectId={projectId}
        services={services}
        observationsByCompetitor={observationsByCompetitor}
        readOnly={readOnly}
        onChanged={onChanged}
      />
    </div>
  );
}

function Metric({
  label,
  value,
  foot,
}: {
  label: string;
  value: string;
  foot: string;
}) {
  return (
    <div className={card}>
      <div className="text-xs uppercase tracking-wide text-[#737687]">{label}</div>
      <div className="mt-1 text-3xl font-bold text-[#20212a]">{value}</div>
      <div className="mt-1 text-xs text-[#737687]">{foot}</div>
    </div>
  );
}

function ServiceCatalog({
  token,
  projectId,
  services,
  observationsByCompetitor,
  readOnly,
  onChanged,
}: {
  token: string;
  projectId: string;
  services: Service[];
  observationsByCompetitor: Record<string, Observation[]>;
  readOnly: boolean;
  onChanged: () => void;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      setName("");
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Request failed");
    }
  }

  const usage = (serviceId: string) =>
    Object.values(observationsByCompetitor)
      .flat()
      .filter((o) => o.service_id === serviceId).length;

  return (
    <section className={card}>
      <h3 className="mb-3 text-sm font-semibold">Service catalog</h3>
      <p className="mb-3 text-xs text-[#737687]">
        Canonical offerings for this market — defined once per project so
        price comparisons stay apples-to-apples. Names dedupe
        case-insensitively; a service in use by observations cannot be
        deleted.
      </p>
      {error ? (
        <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      <ul className="mb-3 flex flex-wrap gap-2">
        {services.length === 0 ? (
          <li className="text-sm text-[#737687]">No services defined yet.</li>
        ) : (
          services.map((service) => (
            <li
              key={service.id}
              className="flex items-center gap-2 rounded-full border border-[#e7e8ef] bg-[#f6f7fb] px-3 py-1.5 text-sm"
            >
              {service.name}
              <span className="text-xs text-[#737687]">{usage(service.id)} uses</span>
              {!readOnly && (
                <button
                  onClick={() =>
                    run(() => deleteService(token, projectId, service.id))
                  }
                  className="text-xs text-red-600 hover:underline"
                >
                  remove
                </button>
              )}
            </li>
          ))
        )}
      </ul>
      {!readOnly && (
        <div className="flex gap-2">
          <input
            className={`${inputCls} max-w-xs`}
            placeholder="New service name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button
            className={btnSecondary}
            disabled={!name.trim()}
            onClick={() => run(() => createService(token, projectId, { name: name.trim() }))}
          >
            Add service
          </button>
        </div>
      )}
    </section>
  );
}
