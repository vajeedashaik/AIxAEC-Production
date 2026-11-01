"use client";

import { ErrorState } from "@/components/composites";
import { Button } from "@/components/ui/button";

/** Keeps the sidebar and top bar usable when one screen fails. */
export default function AppError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-4 p-6">
      <ErrorState error={error} title="This screen hit a problem" />
      <div>
        <Button variant="outline" onClick={reset}>
          Try again
        </Button>
      </div>
    </div>
  );
}
