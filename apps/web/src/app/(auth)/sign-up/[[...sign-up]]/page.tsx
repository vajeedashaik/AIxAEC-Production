import { SignUp } from "@clerk/nextjs";
import { Suspense } from "react";

import { Placeholder } from "@/components/placeholder";
import { CLERK_ENABLED } from "@/lib/clerk";

export default function SignUpPage() {
  if (!CLERK_ENABLED)
    return (
      <Placeholder title="Clerk isn't configured" owner="P0">
        Run <code className="numeric">npx clerk@latest init --accountless</code> in <code className="numeric">apps/web</code> for
        temporary dev keys, or add your keys to <code className="numeric">.env.local</code> (see .env.example).
      </Placeholder>
    );
  return (
    <main className="grid min-h-screen place-items-center p-6">
      {/* Clerk reads the URL at runtime; Cache Components requires that under Suspense. */}
      <Suspense>
        <SignUp />
      </Suspense>
    </main>
  );
}
