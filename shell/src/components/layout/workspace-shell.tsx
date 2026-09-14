"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Organization } from "@/lib/api/types";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

/** One entry in the dark workspace sidebar (mirrors the mockup's nav). */
export interface WorkspaceNavItem {
  key: string;
  label: string;
  count?: number;
  disabledNote?: string;
}

interface WorkspaceShellProps {
  email: string;
  orgs: Organization[];
  currentOrgId: string;
  crumbs: [string, string];
  navItems: WorkspaceNavItem[];
  activeNav: string;
  onNav: (key: string) => void;
  actions?: ReactNode;
  children: ReactNode;
}

/** Full-height workspace chrome modeled on
 *  planning/competitor-intelligence-workspace.html: dark sidebar with
 *  org switcher + module nav, light content area with a breadcrumb
 *  topbar. Used by the per-phase module pages (research, competitors). */
export function WorkspaceShell({
  email,
  orgs,
  currentOrgId,
  crumbs,
  navItems,
  activeNav,
  onNav,
  actions,
  children,
}: WorkspaceShellProps) {
  const router = useRouter();
  const currentOrg = orgs.find((org) => org.id === currentOrgId);

  async function signOut() {
    await createClient().auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="flex min-h-screen bg-[#f6f7fb]">
      <aside className="sticky top-0 flex h-screen w-64 flex-col bg-[#171820] px-3.5 py-5 text-[#e9e9f2]">
        <Link href="/org" className="flex items-center gap-2.5 px-2.5 pb-5 font-bold">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-[#8f80f7] to-[#6d5ce7] text-sm text-white">
            OI
          </span>
          Open Intel
        </Link>

        <DropdownMenu>
          <div className="mx-1 mb-5 rounded-xl border border-[#32343e] bg-[#22232c] p-2.5">
            <div className="mb-1.5 text-xs text-[#999cab]">Organization</div>
            <DropdownMenuTrigger className="flex w-full items-center justify-between text-sm font-semibold">
              <span className="truncate">{currentOrg?.name ?? "Organizations"}</span>
              <span aria-hidden>⌄</span>
            </DropdownMenuTrigger>
          </div>
          <DropdownMenuContent>
            <DropdownMenuLabel>Switch organization</DropdownMenuLabel>
            {orgs.map((org) => (
              <DropdownMenuItem
                key={org.id}
                onSelect={() => router.push(`/org/${org.id}`)}
              >
                <span className={cn(org.id === currentOrgId && "font-semibold")}>
                  {org.name}
                </span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <nav className="flex-1">
          {navItems.map((item) =>
            item.disabledNote ? (
              <span
                key={item.key}
                title={`${item.label} arrives in ${item.disabledNote}`}
                className="flex w-full cursor-not-allowed items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm text-[#5f616e]"
              >
                {item.label}
                <span className="ml-auto text-xs">({item.disabledNote})</span>
              </span>
            ) : (
              <button
                key={item.key}
                onClick={() => onNav(item.key)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm",
                  item.key === activeNav
                    ? "bg-[#302d48] text-white"
                    : "text-[#aeb0bc] hover:bg-[#23242d] hover:text-white",
                )}
              >
                {item.label}
                {item.count != null && (
                  <span className="ml-auto text-xs text-[#8f91a0]">{item.count}</span>
                )}
              </button>
            ),
          )}
        </nav>

        <div className="mt-auto">
          <div className="flex items-center gap-2.5 px-2.5 py-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-[#ffe3b5] text-xs font-bold text-[#744a16]">
              {initials(email)}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm">{email}</span>
            </span>
            <button
              onClick={signOut}
              className="ml-auto text-xs text-[#8f91a0] hover:text-white"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <header className="flex h-14 items-center justify-between border-b border-[#e7e8ef] bg-white px-6">
          <div className="flex items-center gap-2 text-sm">
            <span className="text-[#737687]">{crumbs[0]}</span>
            <span aria-hidden>›</span>
            <strong className="font-semibold text-[#20212a]">{crumbs[1]}</strong>
          </div>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
        <div className="px-6 py-6">{children}</div>
      </main>
    </div>
  );
}

function initials(email: string): string {
  const name = email.split("@")[0] ?? "?";
  return name.slice(0, 2).toUpperCase();
}
