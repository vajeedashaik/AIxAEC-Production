"use client";

import { MoreHorizontalIcon, Trash2Icon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState, type KeyboardEvent } from "react";

import { ConfirmDialog, ErrorState, ICON_STROKE } from "@/components/composites";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { UploadDropzone } from "@/features/upload/dropzone";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { FloorplanList } from "./floorplan-list";
import { projectFormSchema, useDeleteProject, useProject, useUpdateProject } from "./hooks";

/** Text that becomes a field on click. Enter or blur saves, Escape cancels; an invalid value stays open with its message. */
function InlineEdit({
  value,
  label,
  placeholder,
  multiline,
  validate,
  onSave,
  displayClassName,
  as: Tag = "span",
}: {
  value: string;
  label: string;
  placeholder?: string;
  multiline?: boolean;
  validate: (next: string) => string | null;
  onSave: (next: string) => void;
  displayClassName?: string;
  as?: "h1" | "span";
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const display = useRef<HTMLButtonElement>(null);
  const skipBlur = useRef(false);

  const close = () => {
    skipBlur.current = true; // unmounting the focused field fires blur in some browsers
    setDraft(null);
    setProblem(null);
    requestAnimationFrame(() => display.current?.focus());
  };
  const commit = () => {
    if (draft === null) return;
    const next = draft.trim();
    const error = validate(next);
    if (error) return setProblem(error);
    if (next !== value) onSave(next);
    close();
  };
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") close();
    if (e.key === "Enter" && !(multiline && e.shiftKey)) {
      e.preventDefault();
      commit();
    }
  };

  if (draft === null) {
    const button = (
      <button ref={display} type="button" aria-label={`Edit ${label}: ${value || "empty"}`} onClick={() => ((skipBlur.current = false), setDraft(value))} className={cn("-mx-1.5 max-w-full cursor-text rounded-md px-1.5 text-left [overflow-wrap:anywhere] transition-colors duration-(--duration-instant) hover:bg-accent", displayClassName, !value && "text-muted-foreground")}>
        {value || placeholder}
      </button>
    );
    return Tag === "h1" ? <h1 className={cn("w-full", displayClassName)}>{button}</h1> : button;
  }
  const Field = multiline ? Textarea : Input;
  return (
    <div className="max-w-2xl">
      <Field
        autoFocus
        aria-label={label}
        aria-invalid={!!problem}
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => !skipBlur.current && commit()}
        className={cn(!multiline && "h-9 md:text-lg font-medium")}
      />
      {problem && (
        <p role="alert" className="mt-1 text-ui text-danger">
          {problem}
        </p>
      )}
    </div>
  );
}

const fieldProblem = (field: "name" | "description", value: string) => {
  const result = projectFormSchema.shape[field].safeParse(value);
  return result.success ? null : result.error.issues[0].message;
};

export function ProjectDetail({ projectId }: { projectId: string }) {
  const router = useRouter();
  const { data: project, error, isPending, refetch } = useProject(projectId);
  const update = useUpdateProject(projectId);
  const remove = useDeleteProject();
  const [confirming, setConfirming] = useState(false);

  if (error) return <ErrorState className="m-6" error={error} onRetry={() => refetch()} title="Couldn't load this project" />;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-6 md:px-6">
      {isPending ? (
        <div role="status" aria-label="Loading project" className="flex flex-col gap-2">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-5 w-96 max-w-full" />
        </div>
      ) : (
        <header className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 flex-1 flex-col items-start gap-1">
            <InlineEdit as="h1" label="project name" value={project.name} validate={(v) => fieldProblem("name", v)} onSave={(name) => update.mutate({ name })} displayClassName="text-2xl font-semibold tracking-tight" />
            <InlineEdit label="project description" multiline value={project.description ?? ""} placeholder="Add a description" validate={(v) => fieldProblem("description", v)} onSave={(d) => update.mutate({ description: d || null })} displayClassName="text-sm text-muted-foreground" />
            <p className="numeric mt-1 text-micro text-muted-foreground">created {formatDate(project.created_at)}</p>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="More project actions">
                <MoreHorizontalIcon strokeWidth={ICON_STROKE} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem variant="destructive" onSelect={() => setConfirming(true)}>
                <Trash2Icon strokeWidth={ICON_STROKE} />
                Delete project
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <ConfirmDialog
            open={confirming}
            onOpenChange={setConfirming}
            title={`Delete ${project.name}?`}
            description="This permanently deletes the project, its floor plans and every version of each model."
            confirmLabel="Delete project"
            onConfirm={async () => {
              await remove.mutateAsync(projectId);
              router.replace("/projects");
            }}
          />
        </header>
      )}

      <UploadDropzone projectId={projectId} className="mt-6" />

      <section aria-labelledby="plans-heading" className="mt-8">
        <h2 id="plans-heading" className="mb-2 text-base font-medium">
          Floor plans
        </h2>
        <FloorplanList projectId={projectId} />
      </section>
    </div>
  );
}
