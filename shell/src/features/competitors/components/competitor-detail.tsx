"use client";

import { useState } from "react";

import {
  addEvidence,
  createLocation,
  createObservation,
  deleteEvidence,
  deleteLocation,
} from "@/lib/api/client";
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
  StateBadge,
} from "@/components/workspace/bits";

interface CompetitorDetailProps {
  token: string;
  projectId: string;
  competitor: Competitor;
  locations: Location[];
  services: Service[];
  observations: Observation[];
  evidence: EvidenceLink[];
  readOnly: boolean;
  onChanged: () => void;
}

/** Inline expansion of one competitor: branch locations, price
 *  observations (add + history), and evidence links. */
export function CompetitorDetail({
  token,
  projectId,
  competitor,
  locations,
  services,
  observations,
  evidence,
  readOnly,
  onChanged,
}: CompetitorDetailProps) {
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
    <div className="space-y-4 border-t border-[#e7e8ef] px-5 py-4">
      {error ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      ) : null}
      {competitor.website || competitor.notes ? (
        <p className="text-sm text-[#737687]">
          {competitor.website ? (
            <a
              href={competitor.website}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#6d5ce7] hover:underline"
            >
              {competitor.website}
            </a>
          ) : null}
          {competitor.website && competitor.notes ? " · " : null}
          {competitor.notes}
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <LocationsCard
          locations={locations}
          readOnly={readOnly}
          onAdd={(input) =>
            run(() => createLocation(token, projectId, competitor.id, input))
          }
          onDelete={(locationId) =>
            run(() => deleteLocation(token, projectId, competitor.id, locationId))
          }
        />
        <ObservationsCard
          services={services}
          locations={locations}
          observations={observations}
          readOnly={readOnly}
          onAdd={(input) =>
            run(() => createObservation(token, projectId, competitor.id, input))
          }
        />
        <EvidenceCard
          evidence={evidence}
          readOnly={readOnly}
          onAdd={(input) =>
            run(() => addEvidence(token, projectId, competitor.id, input))
          }
          onDelete={(evidenceId) =>
            run(() => deleteEvidence(token, projectId, competitor.id, evidenceId))
          }
        />
      </div>
    </div>
  );
}

function LocationsCard({
  locations,
  readOnly,
  onAdd,
  onDelete,
}: {
  locations: Location[];
  readOnly: boolean;
  onAdd: (input: { name: string; address?: string | null }) => void;
  onDelete: (locationId: string) => void;
}) {
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  return (
    <section className={card}>
      <h3 className="mb-3 text-sm font-semibold">Branches</h3>
      <ul className="mb-3 space-y-1.5">
        {locations.length === 0 ? (
          <li className="text-sm text-[#737687]">No branches yet.</li>
        ) : (
          locations.map((location) => (
            <li key={location.id} className="flex items-center gap-2 text-sm">
              <span className="min-w-0 flex-1 truncate">
                {location.name}
                {location.address ? (
                  <span className="text-[#737687]"> — {location.address}</span>
                ) : null}
              </span>
              {!readOnly && (
                <button
                  onClick={() => onDelete(location.id)}
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
        <div className="space-y-2">
          <input
            className={inputCls}
            placeholder="Branch name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className={inputCls}
            placeholder="Address (optional)"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
          />
          <button
            className={btnSecondary}
            disabled={!name.trim()}
            onClick={() => {
              onAdd({ name: name.trim(), address: address.trim() || null });
              setName("");
              setAddress("");
            }}
          >
            Add branch
          </button>
        </div>
      )}
    </section>
  );
}

function ObservationsCard({
  services,
  locations,
  observations,
  readOnly,
  onAdd,
}: {
  services: Service[];
  locations: Location[];
  observations: Observation[];
  readOnly: boolean;
  onAdd: (input: {
    service_id: string | null;
    location_id: string | null;
    price_amount: string;
    price_currency: string;
    observed_on: string;
  }) => void;
}) {
  const [serviceId, setServiceId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("MYR");
  const [observedOn, setObservedOn] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  return (
    <section className={card}>
      <h3 className="mb-3 text-sm font-semibold">Price observations</h3>
      <ul className="mb-3 space-y-1.5">
        {observations.length === 0 ? (
          <li className="text-sm text-[#737687]">No observations yet.</li>
        ) : (
          [...observations].reverse().map((observation) => (
            <li key={observation.id} className="flex items-center gap-2 text-sm">
              <span className="min-w-0 flex-1">
                {formatPrice(observation)}
                <span className="text-[#737687]">
                  {" "}
                  · {serviceName(services, observation.service_id)} ·{" "}
                  {observation.observed_on}
                </span>
              </span>
              <StateBadge state={observation.approval_state} />
            </li>
          ))
        )}
      </ul>
      {!readOnly && (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <select
              className={inputCls}
              value={serviceId}
              onChange={(e) => setServiceId(e.target.value)}
            >
              <option value="">Service (optional)</option>
              {services.map((service) => (
                <option key={service.id} value={service.id}>
                  {service.name}
                </option>
              ))}
            </select>
            <select
              className={inputCls}
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
            >
              <option value="">Branch (optional)</option>
              {locations.map((location) => (
                <option key={location.id} value={location.id}>
                  {location.name}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <input
              className={inputCls}
              placeholder="88.00"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
            <input
              className={inputCls}
              placeholder="MYR"
              maxLength={3}
              value={currency}
              onChange={(e) => setCurrency(e.target.value.toUpperCase())}
            />
            <input
              type="date"
              className={inputCls}
              value={observedOn}
              onChange={(e) => setObservedOn(e.target.value)}
            />
          </div>
          <button
            className={btnSecondary}
            disabled={!price.trim() || currency.trim().length !== 3}
            onClick={() =>
              onAdd({
                service_id: serviceId || null,
                location_id: locationId || null,
                price_amount: price.trim(),
                price_currency: currency.trim().toUpperCase(),
                observed_on: observedOn,
              })
            }
          >
            Add observation (lands pending)
          </button>
        </div>
      )}
    </section>
  );
}

function EvidenceCard({
  evidence,
  readOnly,
  onAdd,
  onDelete,
}: {
  evidence: EvidenceLink[];
  readOnly: boolean;
  onAdd: (input: {
    target_kind: "source" | "notebook";
    target_id: string;
    excerpt: string | null;
  }) => void;
  onDelete: (evidenceId: string) => void;
}) {
  const [kind, setKind] = useState<"source" | "notebook">("source");
  const [targetId, setTargetId] = useState("");
  const [excerpt, setExcerpt] = useState("");
  return (
    <section className={card}>
      <h3 className="mb-3 text-sm font-semibold">Evidence</h3>
      <ul className="mb-3 space-y-1.5">
        {evidence.length === 0 ? (
          <li className="text-sm text-[#737687]">No evidence attached.</li>
        ) : (
          evidence.map((link) => (
            <li key={link.id} className="text-sm">
              <span className="mr-1.5 inline-block rounded bg-[#f0edff] px-1.5 py-0.5 text-xs font-semibold text-[#5a48c8]">
                {link.target_kind}
              </span>
              <span className="break-all text-xs text-[#737687]">{link.target_id}</span>
              {link.excerpt ? (
                <span className="block truncate text-[#737687]">
                  “{link.excerpt}”
                </span>
              ) : null}
              {!readOnly && (
                <button
                  onClick={() => onDelete(link.id)}
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
        <div className="space-y-2">
          <div className="grid grid-cols-3 gap-2">
            <select
              className={inputCls}
              value={kind}
              onChange={(e) => setKind(e.target.value as "source" | "notebook")}
            >
              <option value="source">source</option>
              <option value="notebook">notebook</option>
            </select>
            <input
              className={`${inputCls} col-span-2`}
              placeholder="Target UUID"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
            />
          </div>
          <input
            className={inputCls}
            placeholder="Excerpt (optional)"
            value={excerpt}
            onChange={(e) => setExcerpt(e.target.value)}
          />
          <button
            className={btnSecondary}
            disabled={!targetId.trim()}
            onClick={() => {
              onAdd({
                target_kind: kind,
                target_id: targetId.trim(),
                excerpt: excerpt.trim() || null,
              });
              setTargetId("");
              setExcerpt("");
            }}
          >
            Attach evidence
          </button>
        </div>
      )}
    </section>
  );
}

function serviceName(services: Service[], id: string | null): string {
  if (!id) return "market level";
  return services.find((s) => s.id === id)?.name ?? "unknown service";
}
