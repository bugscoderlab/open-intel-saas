"use client";

import { ChevronDown, LogOut } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
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

/** Modules not built yet (Phase 2+): rendered unavailable, never erroring
 *  (ticket #19 acceptance: "Navigation reflects disabled modules"). */
const DISABLED_MODULES = [
  { name: "Research", note: "Phase 2" },
  { name: "Competitor Intelligence", note: "Phase 2" },
  { name: "Monitoring", note: "Phase 3" },
  { name: "Analytics", note: "Phase 3" },
] as const;

interface AppShellProps {
  email: string;
  orgs: Organization[];
  currentOrgId: string | null;
  children: ReactNode;
}

export function AppShell({ email, orgs, currentOrgId, children }: AppShellProps) {
  const router = useRouter();
  const currentOrg = orgs.find((org) => org.id === currentOrgId) ?? null;

  async function signOut() {
    await createClient().auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-4">
            <Link href="/org" className="text-lg font-bold text-gray-900">
              Open Intel
            </Link>
            <DropdownMenu>
              <DropdownMenuTrigger>
                <span className="max-w-48 truncate">
                  {currentOrg ? currentOrg.name : "Organizations"}
                </span>
                <ChevronDown className="h-4 w-4 text-gray-500" />
              </DropdownMenuTrigger>
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
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-500">{email}</span>
            <Button variant="ghost" onClick={signOut}>
              <LogOut className="h-4 w-4" /> Sign out
            </Button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-5xl gap-1 px-4 pb-2">
          <NavLink href={currentOrgId ? `/org/${currentOrgId}` : "/org"} active>
            Platform
          </NavLink>
          {DISABLED_MODULES.map((module) => (
            <span
              key={module.name}
              title={`${module.name} is unavailable in this slice (${module.note})`}
              className="cursor-not-allowed rounded-md px-3 py-1.5 text-sm text-gray-400"
            >
              {module.name}
              <span className="ml-1 text-xs">({module.note})</span>
            </span>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-5xl space-y-6 px-4 py-6">{children}</main>
    </div>
  );
}

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active?: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-md px-3 py-1.5 text-sm font-medium",
        active ? "bg-blue-50 text-blue-700" : "text-gray-600 hover:bg-gray-100",
      )}
    >
      {children}
    </Link>
  );
}
