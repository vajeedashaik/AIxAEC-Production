import { Placeholder } from "@/components/placeholder";

import { ProjectsProbe } from "./projects-probe";

export const metadata = { title: "Projects" };

export default function ProjectsPage() {
  return (
    <Placeholder title="Projects" owner="P5">
      <ProjectsProbe />
    </Placeholder>
  );
}
