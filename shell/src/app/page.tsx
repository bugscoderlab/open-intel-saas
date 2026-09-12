import { redirect } from "next/navigation";

import { listOrganizations } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/server";

/** / redirects by auth state: sign-in for strangers, the first
 *  organization (or the picker) for members. */
export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  try {
    const orgs = await listOrganizations(session.access_token);
    if (orgs.length > 0) redirect(`/org/${orgs[0].id}`);
  } catch {
    // Backend unreachable: fall through to the org picker, which shows the
    // error state rather than redirect-looping.
  }
  redirect("/org");
}
