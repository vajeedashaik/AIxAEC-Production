import { Suspense } from "react";

import { SkeletonList } from "@/components/composites";
import { ProjectsView } from "@/features/projects/projects-view";

export const metadata = { title: "Projects" };

export default function ProjectsPage() {
  return (
    <Suspense fallback={<SkeletonList rows={5} label="Loading projects" className="p-6" />}>
      <ProjectsView />
    </Suspense>
  );
}
