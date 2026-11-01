import { Suspense } from "react";

import { CanvasSkeleton } from "@/features/workspace/Workspace";
import { WorkspaceRoute } from "@/features/workspace/WorkspaceRoute";

export const metadata = { title: "Floor plan" };

export default function FloorplanWorkspacePage() {
  return (
    <Suspense
      fallback={
        <div className="h-[calc(100dvh-var(--topbar-h))]">
          <CanvasSkeleton />
        </div>
      }
    >
      <WorkspaceRoute />
    </Suspense>
  );
}
