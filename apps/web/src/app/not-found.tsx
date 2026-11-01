import Link from "next/link";

import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";

export const metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-xl flex-col justify-center gap-4 p-6">
      <Logo className="mb-6 text-base" />
      <h1 className="text-2xl font-semibold tracking-tight">This page isn&apos;t on the plan</h1>
      <p className="text-sm text-muted-foreground">The link may be wrong, or what it pointed to was deleted.</p>
      <div>
        <Button asChild>
          <Link href="/dashboard">Go to dashboard</Link>
        </Button>
      </div>
    </main>
  );
}
