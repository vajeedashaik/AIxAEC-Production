"use client";

import { FolderPlusIcon, LayoutGridIcon, ListIcon, MoreHorizontalIcon, PencilIcon, PlusIcon, SearchIcon, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { ConfirmDialog, EmptyState, ErrorState, ICON_STROKE, PageHeader, SkeletonList } from "@/components/composites";
import { PlanThumb } from "@/components/plan-thumb";
import { useShellActions } from "@/components/shell/shell-actions";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Project } from "@/contracts";
import { formatDate } from "@/lib/format";

import { PAGE_SIZE, useDeleteProject, useProjects } from "./hooks";
import { EditProjectDialog } from "./project-form-dialog";

const SORTS = {
  updated: { label: "Last updated", compare: (a: Project, b: Project) => b.updated_at.localeCompare(a.updated_at) },
  created: { label: "Date created", compare: (a: Project, b: Project) => b.created_at.localeCompare(a.created_at) },
  name: { label: "Name", compare: (a: Project, b: Project) => a.name.localeCompare(b.name) },
  plans: { label: "Most floor plans", compare: (a: Project, b: Project) => b.floorplan_count - a.floorplan_count },
};
type SortKey = keyof typeof SORTS;

export function filterAndSort(projects: Project[], query: string, sort: SortKey) {
  const q = query.trim().toLowerCase();
  const hits = q ? projects.filter((p) => p.name.toLowerCase().includes(q) || p.description?.toLowerCase().includes(q)) : projects;
  return [...hits].sort(SORTS[sort].compare);
}

const plansLabel = (n: number) => `${n} ${n === 1 ? "plan" : "plans"}`;

function ProjectMenu({ project, onRename, onDelete }: { project: Project; onRename: () => void; onDelete: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`More actions for ${project.name}`}>
          <MoreHorizontalIcon strokeWidth={ICON_STROKE} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={onRename}>
          <PencilIcon strokeWidth={ICON_STROKE} />
          Rename
        </DropdownMenuItem>
        <DropdownMenuItem variant="destructive" onSelect={onDelete}>
          <Trash2Icon strokeWidth={ICON_STROKE} />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ProjectItem({ project, view, onAfterDelete }: { project: Project; view: "grid" | "list"; onAfterDelete: () => void }) {
  const [dialog, setDialog] = useState<"rename" | "delete" | null>(null);
  const remove = useDeleteProject();
  const href = `/projects/${project.id}`;
  const menu = <ProjectMenu project={project} onRename={() => setDialog("rename")} onDelete={() => setDialog("delete")} />;

  return (
    <li className={view === "grid" ? "group relative flex flex-col overflow-hidden rounded-lg border bg-card transition-colors duration-(--duration-fast) hover:border-border-strong" : "flex items-center gap-3 py-(--row-gap)"}>
      {view === "grid" ? (
        <>
          <PlanThumb src={project.thumbnail_url} label={`Latest floor plan in ${project.name}`} className="aspect-[3/2] w-full rounded-none border-0 border-b" />
          <div className="flex items-start gap-2 p-3">
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-sm font-medium">
                <Link href={href} className="after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-lg focus-visible:after:outline-2 focus-visible:after:outline-ring">
                  {project.name}
                </Link>
              </h2>
              <p className="numeric mt-1 text-micro text-muted-foreground">
                {plansLabel(project.floorplan_count)} · {formatDate(project.updated_at)}
              </p>
            </div>
            <div className="relative z-10 -mt-1 -mr-1">{menu}</div>
          </div>
        </>
      ) : (
        <>
          <PlanThumb src={project.thumbnail_url} className="h-10 w-14" />
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-ui font-medium">
              <Link href={href} className="hover:underline">
                {project.name}
              </Link>
            </h2>
            {project.description && <p className="truncate text-micro text-muted-foreground">{project.description}</p>}
          </div>
          <span className="numeric w-16 shrink-0 text-right text-micro text-muted-foreground">{plansLabel(project.floorplan_count)}</span>
          <span className="numeric w-24 shrink-0 text-right text-micro text-muted-foreground max-sm:hidden">{formatDate(project.updated_at)}</span>
          {menu}
        </>
      )}
      <EditProjectDialog project={project} open={dialog === "rename"} onOpenChange={(o) => setDialog(o ? "rename" : null)} />
      <ConfirmDialog
        open={dialog === "delete"}
        onOpenChange={(o) => setDialog(o ? "delete" : null)}
        title={`Delete ${project.name}?`}
        description={`This permanently deletes the project and its ${plansLabel(project.floorplan_count)}, including every version of each model.`}
        confirmLabel="Delete project"
        onConfirm={async () => {
          await remove.mutateAsync(project.id);
          onAfterDelete();
        }}
      />
    </li>
  );
}

export function ProjectsView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { createProject } = useShellActions();

  const q = params.get("q") ?? "";
  const view = params.get("view") === "list" ? "list" : "grid";
  const sort = (params.get("sort") as SortKey | null) ?? "updated";
  const page = Math.max(1, Number(params.get("page")) || 1);

  const setParams = (change: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(change)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const { data, error, isPending, refetch } = useProjects(page);
  const shown = useMemo(() => (data ? filterAndSort(data.items, q, SORTS[sort] ? sort : "updated") : []), [data, q, sort]);
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const newButton = (
    <Button onClick={createProject}>
      <PlusIcon strokeWidth={ICON_STROKE} />
      New project
    </Button>
  );

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-6">
      <PageHeader title="Projects" actions={newButton} />

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <div className="relative min-w-48 flex-1 sm:max-w-xs">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" strokeWidth={ICON_STROKE} aria-hidden />
          <Input type="search" aria-label="Search projects" placeholder="Search projects" className="pl-8" value={q} onChange={(e) => setParams({ q: e.target.value || null })} />
        </div>
        <Select value={SORTS[sort] ? sort : "updated"} onValueChange={(v) => setParams({ sort: v === "updated" ? null : v })}>
          <SelectTrigger aria-label="Sort projects" className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(SORTS).map(([key, s]) => (
              <SelectItem key={key} value={key}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <ToggleGroup type="single" aria-label="Layout" variant="outline" value={view} onValueChange={(v) => v && setParams({ view: v === "grid" ? null : v })} className="ml-auto">
          <ToggleGroupItem value="grid" aria-label="Grid">
            <LayoutGridIcon strokeWidth={ICON_STROKE} />
          </ToggleGroupItem>
          <ToggleGroupItem value="list" aria-label="List">
            <ListIcon strokeWidth={ICON_STROKE} />
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      <div className="mt-5">
        {isPending ? (
          <SkeletonList rows={view === "grid" ? 6 : 5} label="Loading projects" className={view === "grid" ? "grid gap-3 sm:grid-cols-2 lg:grid-cols-3" : undefined} rowClassName={view === "grid" ? "h-52" : "h-12"} />
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} title="Couldn't load projects" />
        ) : data.total === 0 ? (
          <EmptyState icon={FolderPlusIcon} title="No projects yet" description="A project holds the floor plans of one building or job. Create one, then upload a drawing." action={newButton} />
        ) : shown.length === 0 ? (
          <EmptyState
            icon={SearchIcon}
            title={`Nothing matches “${q}”`}
            description={data.total > PAGE_SIZE ? "Search covers this page of results. Try another page or a different word." : "Check the spelling or try a different word."}
            action={
              <Button variant="outline" onClick={() => setParams({ q: null })}>
                Clear search
              </Button>
            }
          />
        ) : (
          <ul aria-label="Projects" className={view === "grid" ? "grid gap-3 sm:grid-cols-2 lg:grid-cols-3" : "divide-y"}>
            {shown.map((p) => (
              <ProjectItem key={p.id} project={p} view={view} onAfterDelete={() => data.items.length === 1 && page > 1 && setParams({ page: String(page - 1) })} />
            ))}
          </ul>
        )}
      </div>

      {data && pages > 1 && (
        <nav aria-label="Pagination" className="mt-5 flex items-center justify-between gap-3">
          <p className="numeric text-micro text-muted-foreground">
            page {page} of {pages} · {data.total} projects
          </p>
          <div className="flex gap-2">
            <Button variant="outline" disabled={page <= 1} onClick={() => setParams({ page: page > 2 ? String(page - 1) : null })}>
              Previous
            </Button>
            <Button variant="outline" disabled={page >= pages} onClick={() => setParams({ page: String(page + 1) })}>
              Next
            </Button>
          </div>
        </nav>
      )}
    </div>
  );
}
