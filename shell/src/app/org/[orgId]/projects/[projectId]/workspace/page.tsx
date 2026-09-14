import { redirect } from "next/navigation";

/** The competitor-intelligence workspace folded into the unified project
 *  workspace (PDR-004, spec #36) — old deep links land on the Overview. */
export default async function CompetitorWorkspaceRedirect({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = await params;
  redirect(`/org/${orgId}/projects/${projectId}?view=overview`);
}
