import { SignUp } from "@clerk/nextjs";
import { Suspense } from "react";

import { CLERK_ENABLED } from "@/lib/clerk";

import { ClerkNotConfigured } from "../../not-configured";

export const metadata = { title: "Create account" };

export default function SignUpPage() {
  if (!CLERK_ENABLED) return <ClerkNotConfigured />;
  return (
    <Suspense>
      <SignUp fallbackRedirectUrl="/dashboard" signInFallbackRedirectUrl="/dashboard" signInUrl="/sign-in" />
    </Suspense>
  );
}
