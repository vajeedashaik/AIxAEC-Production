"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { z } from "zod";

import type { FloorPlan, Job, Project, ProjectPage, ProjectUpdate } from "@/contracts";
import { queryKeys, useApi } from "@/lib/api";
import { ApiError } from "@/lib/api/client";
import { describeError } from "@/lib/errors";

export const PAGE_SIZE = 20;

// Same bounds as ProjectCreate / ProjectUpdate in the contract.
export const projectFormSchema = z.object({
  name: z.string().trim().min(1, "Give the project a name.").max(200, "Keep the name to 200 characters."),
  description: z.string().trim().max(2000, "Keep the description to 2000 characters."),
});

const toastError = (error: unknown) => {
  const copy = describeError(error);
  toast.error(copy.title, { description: copy.description });
};

export function useProjects(page = 1, limit = PAGE_SIZE) {
  const api = useApi();
  const params = { limit, offset: (page - 1) * limit };
  return useQuery({ queryKey: queryKeys.projects.list(params), queryFn: ({ signal }) => api.listProjects(params, signal) });
}

export function useProject(projectId: string) {
  const api = useApi();
  return useQuery({ queryKey: queryKeys.projects.detail(projectId), queryFn: ({ signal }) => api.getProject(projectId, signal) });
}

export function useFloorplans(projectId: string) {
  const api = useApi();
  return useQuery({ queryKey: queryKeys.projects.floorplans(projectId), queryFn: ({ signal }) => api.listFloorplans(projectId, signal) });
}

export function useCreateProject() {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createProject,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects.all }),
  });
}

/** Optimistic because a rename can't conflict with anything: roll back and tell the user if the API disagrees. */
export function useUpdateProject(projectId: string) {
  const api = useApi();
  const qc = useQueryClient();
  const listKey = [...queryKeys.projects.all, "list"];
  const detailKey = queryKeys.projects.detail(projectId);
  return useMutation({
    mutationFn: (body: ProjectUpdate) => api.updateProject(projectId, body),
    onMutate: async (body) => {
      await qc.cancelQueries({ queryKey: queryKeys.projects.all });
      const detail = qc.getQueryData<Project>(detailKey);
      const lists = qc.getQueriesData<ProjectPage>({ queryKey: listKey });
      const patch = (p: Project): Project => (p.id === projectId ? { ...p, ...(body.name ? { name: body.name } : {}), ...("description" in body ? { description: body.description ?? null } : {}) } : p);
      if (detail) qc.setQueryData(detailKey, patch(detail));
      qc.setQueriesData<ProjectPage>({ queryKey: listKey }, (page) => page && { ...page, items: page.items.map(patch) });
      return { detail, lists };
    },
    onError: (error, _body, context) => {
      if (context?.detail) qc.setQueryData(detailKey, context.detail);
      context?.lists.forEach(([key, data]) => qc.setQueryData(key, data));
      toastError(error);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: queryKeys.projects.all }),
  });
}

export function useDeleteProject() {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.deleteProject,
    onSuccess: async (_data, projectId) => {
      qc.removeQueries({ queryKey: queryKeys.projects.detail(projectId) });
      await qc.invalidateQueries({ queryKey: queryKeys.projects.all });
      toast.success("Project deleted");
    },
    onError: toastError,
  });
}

export function useDeleteFloorplan() {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.deleteFloorplan,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: queryKeys.projects.all });
      toast.success("Floor plan deleted");
    },
    onError: toastError,
  });
}

/** Start or retry processing. A 409 means the worker already has it, which is what the user wanted. */
export function useProcessFloorplan(projectId: string) {
  const api = useApi();
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries({ queryKey: queryKeys.projects.floorplans(projectId) });
  return useMutation({
    mutationFn: api.processFloorplan,
    onSuccess: (job: Job) => {
      qc.setQueryData(queryKeys.floorplans.job(job.floorplan_id), job);
      qc.setQueryData<FloorPlan[]>(queryKeys.projects.floorplans(projectId), (plans) =>
        plans?.map((p) => (p.id === job.floorplan_id ? { ...p, status: job.status, latest_job: job } : p)),
      );
      return refresh();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "already_processing") {
        toast.info("Already in the queue");
        return refresh();
      }
      toastError(error);
    },
  });
}

/** Signed URL of the plan's preprocessed image, for COMPLETED plans only. */
export function usePlanThumbnail(floorplan: Pick<FloorPlan, "id" | "status">) {
  const api = useApi();
  const { data } = useQuery({
    queryKey: queryKeys.floorplans.artifacts(floorplan.id),
    queryFn: ({ signal }) => api.listArtifacts(floorplan.id, signal),
    enabled: floorplan.status === "COMPLETED",
    staleTime: 10 * 60_000, // signed URLs outlive this; a failed image falls back to paper anyway
  });
  return data?.find((a) => a.kind === "preprocessed")?.url ?? null;
}
