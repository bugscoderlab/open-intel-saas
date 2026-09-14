import type { Observation } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Shared visual bits matching planning/competitor-intelligence-workspace.html. */

export const card =
  "rounded-2xl bg-white p-5 shadow-[0_16px_45px_rgba(29,27,48,.08)]";

export const btnPrimary =
  "rounded-lg bg-[#6d5ce7] px-4 py-2 text-sm font-semibold text-white hover:bg-[#5b4cd6] disabled:opacity-50";

export const btnSecondary =
  "rounded-lg border border-[#e7e8ef] bg-white px-4 py-2 text-sm font-medium text-[#20212a] hover:bg-gray-50 disabled:opacity-50";

export const inputCls =
  "w-full rounded-lg border border-[#e7e8ef] bg-white px-3 py-2 text-sm outline-none focus:border-[#6d5ce7]";

const STATE_STYLES: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800",
  approved: "bg-emerald-100 text-emerald-800",
  rejected: "bg-red-100 text-red-700",
  superseded: "bg-gray-200 text-gray-600",
};

export function StateBadge({ state }: { state: string }) {
  return (
    <span
      className={cn(
        "inline-block rounded-full px-2 py-0.5 text-xs font-semibold",
        STATE_STYLES[state] ?? "bg-gray-100 text-gray-600",
      )}
    >
      {state}
    </span>
  );
}

const LOGO_COLORS = [
  "bg-[#e5e0ff] text-[#5a48c8]",
  "bg-[#d8f3e6] text-[#168765]",
  "bg-[#ffe5ea] text-[#b83b50]",
  "bg-[#ffe3b5] text-[#744a16]",
  "bg-[#d6e9ff] text-[#1d5fb8]",
];

export function Logo({ name }: { name: string }) {
  const initials = name
    .split(/\s+/)
    .map((w) => w[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();
  const color = LOGO_COLORS[(name.charCodeAt(0) ?? 0) % LOGO_COLORS.length];
  return (
    <span
      className={cn(
        "inline-grid h-8 w-8 shrink-0 place-items-center rounded-lg text-xs font-bold",
        color,
      )}
    >
      {initials || "?"}
    </span>
  );
}

export function formatPrice(observation: Observation): string {
  if (!observation.price_amount) return "—";
  const amount = Number(observation.price_amount).toString();
  return `${observation.price_currency ?? ""} ${amount}`.trim();
}

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}
