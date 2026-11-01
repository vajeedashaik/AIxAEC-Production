import { Suspense } from "react";

import { SettingsView } from "@/features/settings/settings-view";

export const metadata = { title: "Settings" };

export default function SettingsPage() {
  // Clerk's <UserProfile/> reads the URL at runtime; Cache Components requires that under Suspense.
  return (
    <Suspense>
      <SettingsView />
    </Suspense>
  );
}
