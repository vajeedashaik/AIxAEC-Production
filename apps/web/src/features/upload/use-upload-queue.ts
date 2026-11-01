"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { queryKeys, useApi } from "@/lib/api";
import { describeError } from "@/lib/errors";

import { fileProblem } from "./validate";

export type UploadStatus = "queued" | "uploading" | "done" | "failed" | "rejected";
export interface UploadItem {
  id: string;
  file: File;
  status: UploadStatus;
  progress: number; // 0..1
  error?: string;
  warnings: string[];
}

/** One upload at a time, in order. Items survive failure so they can be retried. */
export function useUploadQueue(projectId: string) {
  const api = useApi();
  const qc = useQueryClient();
  const [items, setItems] = useState<UploadItem[]>([]);
  const itemsRef = useRef(items);
  const active = useRef<{ id: string; controller: AbortController } | null>(null);

  const patch = useCallback((id: string, change: Partial<UploadItem>) => {
    itemsRef.current = itemsRef.current.map((i) => (i.id === id ? { ...i, ...change } : i));
    setItems(itemsRef.current);
  }, []);

  const pump = useCallback(async () => {
    if (active.current) return;
    for (;;) {
      const next = itemsRef.current.find((i) => i.status === "queued");
      if (!next) return;
      const controller = new AbortController();
      active.current = { id: next.id, controller };
      patch(next.id, { status: "uploading", progress: 0, error: undefined });
      try {
        const plan = await api.uploadFloorplan(projectId, next.file, { signal: controller.signal, onProgress: (progress) => patch(next.id, { progress }) });
        patch(next.id, { status: "done", progress: 1, warnings: plan.warnings });
        await qc.invalidateQueries({ queryKey: queryKeys.projects.all });
      } catch (error) {
        if (!controller.signal.aborted) patch(next.id, { status: "failed", error: describeError(error).description });
      } finally {
        active.current = null;
      }
    }
  }, [api, patch, projectId, qc]);

  const add = useCallback(
    (files: Iterable<File>) => {
      const added = Array.from(files, (file): UploadItem => {
        const error = fileProblem(file) ?? undefined;
        return { id: crypto.randomUUID(), file, status: error ? "rejected" : "queued", progress: 0, error, warnings: [] };
      });
      itemsRef.current = [...itemsRef.current, ...added];
      setItems(itemsRef.current);
      void pump();
    },
    [pump],
  );

  const retry = useCallback(
    (id: string) => {
      patch(id, { status: "queued", progress: 0, error: undefined });
      void pump();
    },
    [patch, pump],
  );

  /** Removes the item; if it is uploading right now, aborts the request first. */
  const remove = useCallback((id: string) => {
    if (active.current?.id === id) active.current.controller.abort();
    itemsRef.current = itemsRef.current.filter((i) => i.id !== id);
    setItems(itemsRef.current);
  }, []);

  // Leaving the page cancels the in-flight upload rather than orphaning a half-sent file.
  useEffect(() => () => active.current?.controller.abort(), []);

  return { items, add, retry, remove };
}
