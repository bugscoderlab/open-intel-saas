import { redirect } from "next/navigation";

/** The research workspace folded into the unified project workspace
 *  (PDR-004, spec #36) — old deep links land on the Notebooks view. */
export default async function ResearchWorkspaceRedirect({
  params,
}: {
  params: Promise<{ orgId: string; projectId: string }>;
}) {
  const { orgId, projectId } = await params;
  redirect(`/org/${orgId}/projects/${projectId}?view=notebooks`);
}
