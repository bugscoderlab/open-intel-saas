import { AcceptInvitation } from "@/features/invitations/components/accept-invitation";

/** Emailed accept link target:
 *  {INVITATION_BASE_URL}/invitations/accept?token=… (backend-built). */
export default async function AcceptInvitationPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      {token ? (
        <AcceptInvitation token={token} />
      ) : (
        <p className="text-sm text-gray-600">
          This invitation link is missing its token.
        </p>
      )}
    </main>
  );
}
