"use client";

import { ErrorState } from "@/components/composites";
import { Button } from "@/components/ui/button";

export default function RootError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-xl flex-col justify-center gap-4 p-6">
      <ErrorState error={error} title="This screen hit a problem" />
      <div>
        <Button variant="outline" onClick={reset}>
          Try again
        </Button>
      </div>
    </main>
  );
}
