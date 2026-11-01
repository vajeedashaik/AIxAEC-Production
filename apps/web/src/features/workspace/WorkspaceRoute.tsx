"use client";

import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

import { Workspace } from "./Workspace";

/** Binds the workspace to the URL. Must render under <Suspense> (useSearchParams with cacheComponents). */
export function WorkspaceRoute() {
  const { projectId, floorplanId } = useParams<{ projectId: string; floorplanId: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const raw = useSearchParams().get("version");
  const parsed = raw === null ? null : Number(raw);
  const version = parsed !== null && Number.isInteger(parsed) && parsed > 0 ? parsed : null;

  const onVersionChange = useCallback(
    (v: number | null) => router.replace(v === null ? pathname : `${pathname}?version=${v}`, { scroll: false }),
    [pathname, router],
  );
  return <Workspace projectId={projectId} floorplanId={floorplanId} version={version} onVersionChange={onVersionChange} />;
}
