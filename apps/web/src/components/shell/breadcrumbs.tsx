"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb";
import { Skeleton } from "@/components/ui/skeleton";
import { queryKeys, useApi } from "@/lib/api";

const TOP: Record<string, string> = { dashboard: "Dashboard", projects: "Projects", settings: "Settings" };

export interface RouteParts {
  top: string | null;
  projectId: string | null;
  floorplanId: string | null;
}

export function parseRoute(pathname: string): RouteParts {
  const [top, projectId, section, floorplanId] = pathname.split("/").filter(Boolean);
  return { top: top && TOP[top] ? top : null, projectId: top === "projects" ? (projectId ?? null) : null, floorplanId: section === "floorplans" ? (floorplanId ?? null) : null };
}

export function Breadcrumbs() {
  const api = useApi();
  const { top, projectId, floorplanId } = parseRoute(usePathname());
  const project = useQuery({ queryKey: queryKeys.projects.detail(projectId ?? ""), queryFn: ({ signal }) => api.getProject(projectId!, signal), enabled: !!projectId });
  const plan = useQuery({ queryKey: queryKeys.floorplans.detail(floorplanId ?? ""), queryFn: ({ signal }) => api.getFloorplan(floorplanId!, signal), enabled: !!floorplanId });

  const crumbs: { key: string; label: React.ReactNode; href?: string }[] = [];
  if (top) crumbs.push({ key: top, label: TOP[top], href: `/${top}` });
  if (projectId) crumbs.push({ key: projectId, label: project.data?.name ?? <Skeleton className="h-4 w-24" />, href: `/projects/${projectId}` });
  if (floorplanId) crumbs.push({ key: floorplanId, label: plan.data?.original_filename ?? <Skeleton className="h-4 w-24" /> });

  return (
    <Breadcrumb className="min-w-0">
      <BreadcrumbList className="flex-nowrap text-ui">
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          return (
            <Fragment key={c.key}>
              {i > 0 && <BreadcrumbSeparator className="max-sm:hidden" />}
              <BreadcrumbItem className={last ? "min-w-0" : "max-sm:hidden"}>
                {last ? (
                  <BreadcrumbPage className="truncate font-medium">{c.label}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink asChild>
                    <Link href={c.href!} className="max-w-48 truncate">
                      {c.label}
                    </Link>
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
