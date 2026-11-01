"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { ArrowRightIcon, FileImageIcon, PlusIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState, ErrorState, ICON_STROKE, PageHeader, SkeletonList, StatTile, StatusBadge } from "@/components/composites";
import { PlanThumb } from "@/components/plan-thumb";
import { useShellActions } from "@/components/shell/shell-actions";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { FloorPlan, Project } from "@/contracts";
import { usePlanThumbnail, useProjects } from "@/features/projects/hooks";
import { queryKeys, useApi } from "@/lib/api";
import { formatDate } from "@/lib/format";

const SCAN_PROJECTS = 6; // Floor plans have no list-all endpoint; recent ones come from the most recent projects.
const RECENT_PLANS = 6;

export function partOfDay(hour: number) {
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

/** Only totals the API can actually support: a count is dropped, not guessed, once it would be partial. */
export function deriveStats(projects: { items: Project[]; total: number }) {
  const complete = projects.items.length === projects.total;
  return {
    projects: projects.total,
    floorplans: complete ? projects.items.reduce((sum, p) => sum + p.floorplan_count, 0) : null,
  };
}

/** Newest plans across the scanned projects, tagged with their project. */
export function recentPlans(lists: { project: Project; plans: FloorPlan[] }[], limit = RECENT_PLANS) {
  return lists
    .flatMap(({ project, plans }) => plans.map((plan) => ({ plan, project })))
    .sort((a, b) => b.plan.created_at.localeCompare(a.plan.created_at))
    .slice(0, limit);
}

function Greeting() {
  const api = useApi();
  const { data } = useQuery({ queryKey: queryKeys.me, queryFn: ({ signal }) => api.me(signal) });
  const [hour] = useState(() => new Date().getHours());
  const name = data?.display_name?.split(" ")[0];
  // Rendered from client state so the prerendered shell never contains a server's time of day.
  return <>{data ? `${partOfDay(hour)}${name ? `, ${name}` : ""}` : <Skeleton className="h-8 w-64" />}</>;
}

function RecentPlanRow({ plan, project }: { plan: FloorPlan; project: Project }) {
  const thumbnail = usePlanThumbnail(plan);
  const href = plan.status === "COMPLETED" ? `/projects/${project.id}/floorplans/${plan.id}` : `/projects/${project.id}`;
  return (
    <li>
      <Link href={href} className="flex items-center gap-3 rounded-md py-(--row-gap) transition-colors duration-(--duration-instant) hover:bg-accent sm:px-2">
        <PlanThumb src={thumbnail} className="h-12 w-16" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-ui font-medium">{plan.original_filename}</span>
          <span className="block truncate text-micro text-muted-foreground">{project.name}</span>
        </span>
        <span className="numeric shrink-0 text-micro text-muted-foreground max-sm:hidden">
          {plan.current_model_version !== null && `v${plan.current_model_version} · `}
          {formatDate(plan.created_at)}
        </span>
        <StatusBadge status={plan.status} />
      </Link>
    </li>
  );
}

function FirstRun({ onCreate }: { onCreate: () => void }) {
  const steps = [
    { title: "Create a project", body: "One building or job. It keeps its plans and their versions together." },
    { title: "Upload a floor plan", body: "A PNG, JPG or PDF. Walls, rooms, doors and windows are detected and typed." },
    { title: "Edit by saying what to change", body: "Type or speak. You preview every edit, and each one is a new version you can undo." },
  ];
  return (
    <section aria-labelledby="first-run" className="mt-6 grid gap-8 rounded-lg border bg-card p-6 lg:grid-cols-[1fr_1.2fr] lg:p-8">
      <div className="flex flex-col items-start gap-4">
        <div>
          <h2 id="first-run" className="text-2xl font-semibold tracking-tight">
            Start with one drawing
          </h2>
          <p className="mt-2 max-w-[44ch] text-sm text-muted-foreground">Everything here hangs off a project. It takes a name, and you can change it later.</p>
        </div>
        <Button size="lg" onClick={onCreate}>
          <PlusIcon strokeWidth={ICON_STROKE} />
          Create your first project
        </Button>
      </div>
      <ol className="flex flex-col gap-4">
        {steps.map((step, i) => (
          <li key={step.title} className="flex gap-3">
            <span aria-hidden className="numeric grid size-6 shrink-0 place-items-center rounded-full border text-micro text-muted-foreground">
              {i + 1}
            </span>
            <span>
              <span className="block text-sm font-medium">{step.title}</span>
              <span className="block text-ui text-muted-foreground">{step.body}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function DashboardView() {
  const api = useApi();
  const { createProject } = useShellActions();
  const projects = useProjects(1, 100);

  const scanned = [...(projects.data?.items ?? [])]
    .filter((p) => p.floorplan_count > 0)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, SCAN_PROJECTS);
  const planQueries = useQueries({
    queries: scanned.map((p) => ({ queryKey: queryKeys.projects.floorplans(p.id), queryFn: ({ signal }: { signal: AbortSignal }) => api.listFloorplans(p.id, signal) })),
  });
  const plansLoading = planQueries.some((q) => q.isPending);
  const plansError = planQueries.find((q) => q.error);
  const recent = recentPlans(scanned.map((project, i) => ({ project, plans: planQueries[i]?.data ?? [] })));
  const stats = projects.data && deriveStats(projects.data);
  const newButton = (
    <Button onClick={createProject}>
      <PlusIcon strokeWidth={ICON_STROKE} />
      New project
    </Button>
  );

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-6">
      <PageHeader title={<Greeting />} actions={projects.data?.total === 0 ? undefined : newButton} />

      {projects.error ? (
        <ErrorState className="mt-6" error={projects.error} onRetry={() => projects.refetch()} title="Couldn't load your projects" />
      ) : projects.data?.total === 0 ? (
        <FirstRun onCreate={createProject} />
      ) : (
        <>
          <dl aria-label="Totals" className="mt-6 flex gap-10 border-b pb-6">
            <StatTile label="Projects" value={stats?.projects ?? null} />
            {(!stats || stats.floorplans !== null) && <StatTile label="Floor plans" value={stats?.floorplans ?? null} />}
          </dl>

          <section aria-labelledby="recent-heading" className="mt-6">
            <div className="mb-2 flex items-center justify-between gap-3">
              <h2 id="recent-heading" className="text-base font-medium">
                Recent floor plans
              </h2>
              <Button asChild variant="ghost" size="sm">
                <Link href="/projects">
                  All projects
                  <ArrowRightIcon strokeWidth={ICON_STROKE} />
                </Link>
              </Button>
            </div>
            {projects.isPending || plansLoading ? (
              <SkeletonList rows={3} label="Loading recent floor plans" />
            ) : plansError ? (
              <ErrorState error={plansError.error} onRetry={() => planQueries.forEach((q) => q.refetch())} title="Couldn't load recent floor plans" />
            ) : recent.length === 0 ? (
              <EmptyState
                icon={FileImageIcon}
                title="No floor plans yet"
                description="Open a project and upload a drawing to see it here."
                action={
                  <Button asChild variant="outline">
                    <Link href="/projects">Go to projects</Link>
                  </Button>
                }
              />
            ) : (
              <ul className="divide-y sm:-mx-2">
                {recent.map(({ plan, project }) => (
                  <RecentPlanRow key={plan.id} plan={plan} project={project} />
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
