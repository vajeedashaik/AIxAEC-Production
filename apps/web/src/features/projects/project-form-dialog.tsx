"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Spinner } from "@/components/composites";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { Project } from "@/contracts";
import { describeError } from "@/lib/errors";

import { projectFormSchema, useCreateProject, useUpdateProject } from "./hooks";

type Errors = { name?: string; description?: string; form?: string };

function ProjectFields({ initial, submitLabel, submit, onDone }: { initial?: Project; submitLabel: string; submit: (body: { name: string; description: string | null }) => Promise<unknown>; onDone: () => void }) {
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const parsed = projectFormSchema.safeParse({ name: form.get("name"), description: form.get("description") });
    if (!parsed.success) {
      const f = parsed.error.flatten().fieldErrors;
      setErrors({ name: f.name?.[0], description: f.description?.[0] });
      return;
    }
    setErrors({});
    setBusy(true);
    try {
      await submit({ name: parsed.data.name, description: parsed.data.description || null });
      onDone();
    } catch (error) {
      setErrors({ form: describeError(error).description });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={onSubmit} noValidate className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="project-name">Name</Label>
        <Input id="project-name" name="name" autoFocus defaultValue={initial?.name} aria-invalid={!!errors.name} aria-describedby={errors.name ? "project-name-error" : undefined} />
        {errors.name && (
          <p id="project-name-error" className="text-ui text-danger">
            {errors.name}
          </p>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="project-description">
          Description <span className="font-normal text-muted-foreground">(optional)</span>
        </Label>
        <Textarea id="project-description" name="description" className="max-h-[40dvh] overflow-y-auto" defaultValue={initial?.description ?? ""} aria-invalid={!!errors.description} aria-describedby={errors.description ? "project-description-error" : undefined} />
        {errors.description && (
          <p id="project-description-error" className="text-ui text-danger">
            {errors.description}
          </p>
        )}
      </div>
      {errors.form && (
        <p role="alert" className="text-ui text-danger">
          {errors.form}
        </p>
      )}
      <DialogFooter>
        <Button type="submit" disabled={busy}>
          {busy && <Spinner />}
          {submitLabel}
        </Button>
      </DialogFooter>
    </form>
  );
}

/** Creates a project, then takes the user to it: the next thing to do there is upload. */
export function CreateProjectDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const create = useCreateProject();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>A project holds the floor plans of one building or job.</DialogDescription>
        </DialogHeader>
        {open && (
          <ProjectFields
            submitLabel="Create project"
            submit={async (body) => {
              const project = await create.mutateAsync(body);
              router.push(`/projects/${project.id}`);
            }}
            onDone={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

export function EditProjectDialog({ project, open, onOpenChange }: { project: Project; open: boolean; onOpenChange: (open: boolean) => void }) {
  const update = useUpdateProject(project.id);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Rename project</DialogTitle>
          <DialogDescription>Change how this project appears across AEC Studio.</DialogDescription>
        </DialogHeader>
        {open && <ProjectFields initial={project} submitLabel="Save" submit={(body) => update.mutateAsync(body)} onDone={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}
