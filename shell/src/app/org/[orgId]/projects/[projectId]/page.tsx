"use client";

import { Suspense } from "react";

import { RequireAuth } from "@/components/layout/require-auth";
import { ProjectWorkspace } from "@/components/workspace/project-workspace";

/** The project route IS the workspace (PDR-004): one screen hosting the
 *  market overview, competitors, review queue, notebooks, sources, search,
 *  and manage views. */
export default function ProjectWorkspacePage() {
  return (
    <RequireAuth>
      {/* useSearchParams (deep-linked view state) needs a Suspense boundary
          at build time. */}
      <Suspense fallback={null}>
        <ProjectWorkspace />
      </Suspense>
    </RequireAuth>
  );
}
