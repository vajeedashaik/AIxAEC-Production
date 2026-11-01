import { SignIn } from "@clerk/nextjs";
import { Suspense } from "react";

import { CLERK_ENABLED } from "@/lib/clerk";

import { ClerkNotConfigured } from "../../not-configured";

export const metadata = { title: "Sign in" };

export default function SignInPage() {
  if (!CLERK_ENABLED) return <ClerkNotConfigured />;
  return (
    // Clerk reads the URL at runtime; Cache Components requires that under Suspense.
    // ?redirect_url (set by the 401 redirect) takes priority over the fallback.
    <Suspense>
      <SignIn fallbackRedirectUrl="/dashboard" signUpFallbackRedirectUrl="/dashboard" signUpUrl="/sign-up" />
    </Suspense>
  );
}
