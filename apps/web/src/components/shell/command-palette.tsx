"use client";

import { useQueries } from "@tanstack/react-query";
import {
  FileImageIcon,
  FolderIcon,
  LayoutDashboardIcon,
  MoonIcon,
  PlusIcon,
  SettingsIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";

import { ICON_STROKE } from "@/components/composites";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useProjects } from "@/features/projects/hooks";
import { queryKeys, useApi } from "@/lib/api";

const PLAN_SCAN = 8; // no list-all endpoint: floor plans come from the most recently updated projects

function usePaletteData(open: boolean) {
  const api = useApi();
  const projects = useProjects(1, 100);
  const withPlans = (projects.data?.items ?? [])
    .filter((p) => p.floorplan_count > 0)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, PLAN_SCAN);
  const lists = useQueries({
    queries: withPlans.map((p) => ({
      queryKey: queryKeys.projects.floorplans(p.id),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        api.listFloorplans(p.id, signal),
      enabled: open,
    })),
  });
  const plans = withPlans.flatMap((project, i) =>
    (lists[i]?.data ?? []).map((plan) => ({ plan, project })),
  );
  return { projects: projects.data?.items ?? [], plans };
}

export function CommandPalette({
  open,
  onOpenChange,
  onCreateProject,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreateProject: () => void;
}) {
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const { projects, plans } = usePaletteData(open);

  const run = (action: () => void) => () => {
    onOpenChange(false);
    action();
  };
  const go = (href: string) => run(() => router.push(href));

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Command palette"
      description="Jump to a project or floor plan, or run a command."
    >
      {/* shadcn's CommandDialog doesn't wrap its children in <Command>; cmdk needs the root for its store. */}
      <Command>
        <CommandInput placeholder="Jump to a project or plan, or run a command" />
        <CommandList>
          <CommandEmpty>Nothing matches. Try a project name.</CommandEmpty>
          <CommandGroup heading="Commands">
            <CommandItem
              value="Create a new project"
              onSelect={run(onCreateProject)}
            >
              <PlusIcon strokeWidth={ICON_STROKE} />
              New project
            </CommandItem>
            <CommandItem
              value="Toggle theme dark light"
              onSelect={run(() =>
                setTheme(resolvedTheme === "dark" ? "light" : "dark"),
              )}
            >
              <MoonIcon strokeWidth={ICON_STROKE} />
              Toggle theme
            </CommandItem>
          </CommandGroup>
          <CommandGroup heading="Go to">
            <CommandItem value="Dashboard" onSelect={go("/dashboard")}>
              <LayoutDashboardIcon strokeWidth={ICON_STROKE} />
              Dashboard
            </CommandItem>
            <CommandItem value="All projects" onSelect={go("/projects")}>
              <FolderIcon strokeWidth={ICON_STROKE} />
              Projects
            </CommandItem>
            <CommandItem value="Settings" onSelect={go("/settings")}>
              <SettingsIcon strokeWidth={ICON_STROKE} />
              Settings
            </CommandItem>
          </CommandGroup>
          {projects.length > 0 && (
            <CommandGroup heading="Projects">
              {projects.map((p) => (
                <CommandItem
                  key={p.id}
                  value={`project ${p.name} ${p.id}`}
                  onSelect={go(`/projects/${p.id}`)}
                >
                  <FolderIcon strokeWidth={ICON_STROKE} />
                  <span className="truncate">{p.name}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {plans.length > 0 && (
            <CommandGroup heading="Floor plans">
              {plans.map(({ plan, project }) => (
                <CommandItem
                  key={plan.id}
                  value={`plan ${plan.original_filename} ${project.name} ${plan.id}`}
                  onSelect={go(
                    plan.status === "COMPLETED"
                      ? `/projects/${project.id}/floorplans/${plan.id}`
                      : `/projects/${project.id}`,
                  )}
                >
                  <FileImageIcon strokeWidth={ICON_STROKE} />
                  <span className="truncate">{plan.original_filename}</span>
                  <span className="ml-auto truncate text-micro text-muted-foreground">
                    {project.name}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
