import Link from "next/link";

import { Card, CardTitle } from "@/components/ui/card";
import { LoginForm } from "@/features/auth/components/login-form";
import { OAuthButtons } from "@/features/auth/components/oauth-buttons";

export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4">
      <Card>
        <CardTitle>Sign in to Open Intel</CardTitle>
        <LoginForm />
        <div className="my-4 text-center text-xs text-gray-400">or</div>
        <OAuthButtons />
        <p className="mt-4 text-sm text-gray-600">
          No account yet?{" "}
          <Link href="/register" className="text-blue-600 hover:underline">
            Register
          </Link>
        </p>
      </Card>
    </main>
  );
}
