import Link from "next/link";

import { Card, CardTitle } from "@/components/ui/card";
import { OAuthButtons } from "@/features/auth/components/oauth-buttons";
import { RegisterForm } from "@/features/auth/components/register-form";

export default function RegisterPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4">
      <Card>
        <CardTitle>Create your Open Intel account</CardTitle>
        <RegisterForm />
        <div className="my-4 text-center text-xs text-gray-400">or</div>
        <OAuthButtons />
        <p className="mt-4 text-sm text-gray-600">
          Already registered?{" "}
          <Link href="/login" className="text-blue-600 hover:underline">
            Sign in
          </Link>
        </p>
      </Card>
    </main>
  );
}
