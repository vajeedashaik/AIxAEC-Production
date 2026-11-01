import { Suspense } from "react";

import { SkeletonList } from "@/components/composites";
import { ProjectDetail } from "@/features/projects/project-detail";

export const metadata = { title: "Project" };

async function Detail({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <ProjectDetail projectId={projectId} />;
}

export default function ProjectPage({ params }: PageProps<"/projects/[projectId]">) {
  return (
    <Suspense fallback={<SkeletonList rows={3} label="Loading project" className="p-6" />}>
      <Detail params={params} />
    </Suspense>
  );
}
