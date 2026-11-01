import Link from "next/link";

import { Placeholder } from "@/components/placeholder";
import { Button } from "@/components/ui/button";

export default function LandingPage() {
  return (
    <main className="flex min-h-screen flex-col">
      <Placeholder title="AEC Studio" owner="P5">
        <p>Upload a floor plan, get a structured building model, edit it by text, voice or click.</p>
        <div className="mt-6 flex gap-2">
          <Button asChild>
            <Link href="/sign-in">Sign in</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/dashboard">Open dashboard</Link>
          </Button>
        </div>
      </Placeholder>
    </main>
  );
}
