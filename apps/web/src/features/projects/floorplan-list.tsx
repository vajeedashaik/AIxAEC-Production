"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangleIcon, DownloadIcon, FileImageIcon, MoreHorizontalIcon, PlayIcon, RotateCcwIcon, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ConfirmDialog, EmptyState, ErrorState, ICON_STROKE, SkeletonList, Spinner, StatusBadge } from "@/components/composites";
import { PlanThumb } from "@/components/plan-thumb";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import type { FloorPlan } from "@/contracts";
import { queryKeys, useApi } from "@/lib/api";
import { fileKind, formatBytes, formatDate } from "@/lib/format";

import { useDeleteFloorplan, useFloorplans, usePlanThumbnail, useProcessFloorplan } from "./hooks";
import { isLive, isRunning, pollInterval } from "./job-poll";
import { ProcessingTimeline } from "./processing-timeline";

/** Polls while the plan is live. When the job finishes, the list refetches so the row picks up its model version. */
function useLiveJob(plan: FloorPlan) {
  const api = useApi();
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: queryKeys.floorplans.job(plan.id),
    queryFn: ({ signal }) => api.getJob(plan.id, signal),
    initialData: plan.latest_job ?? undefined,
    enabled: isLive(plan.status),
    refetchInterval: (q) => pollInterval(q.state.data, Date.now()),
  });
  const job = query.data ?? plan.latest_job;
  const finished = isLive(plan.status) && job && !isLive(job.status);
  useEffect(() => {
    if (finished) qc.invalidateQueries({ queryKey: queryKeys.projects.all });
  }, [finished, qc]);
  return { job, polledAt: query.dataUpdatedAt };
}

function FloorplanRow({ plan }: { plan: FloorPlan }) {
  const { job, polledAt } = useLiveJob(plan);
  const process = useProcessFloorplan(plan.project_id);
  const remove = useDeleteFloorplan();
  const thumbnail = usePlanThumbnail(plan);
  const [confirming, setConfirming] = useState(false);

  const status = job && isLive(plan.status) ? job.status : plan.status;
  const href = `/projects/${plan.project_id}/floorplans/${plan.id}`;
  const canOpen = plan.status === "COMPLETED";
  const canStart = status === "PENDING" && !(job && isRunning(job));
  const degraded = job?.stages.filter((s) => s.status === "degraded").length ?? 0;

  return (
    <li className="py-(--row-gap)">
      <div className="flex items-start gap-3">
        <PlanThumb src={thumbnail} label={`Preview of ${plan.original_filename}`} className="h-16 w-20" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="min-w-0 truncate text-sm font-medium">
              {canOpen ? (
                <Link href={href} className="hover:underline">
                  {plan.original_filename}
                </Link>
              ) : (
                plan.original_filename
              )}
            </h3>
            <StatusBadge status={status} />
          </div>
          <p className="numeric mt-1 flex flex-wrap gap-x-2 text-micro text-muted-foreground">
            <span>upload {plan.version}</span>
            {plan.current_model_version !== null && <span>model v{plan.current_model_version}</span>}
            <span>{fileKind(plan.content_type)}</span>
            <span>{formatBytes(plan.size_bytes)}</span>
            <span>{formatDate(plan.created_at)}</span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {canOpen && (
            <Button asChild variant="outline" className="max-sm:hidden">
              <Link href={href}>Open plan</Link>
            </Button>
          )}
          {canStart && (
            <Button disabled={process.isPending} onClick={() => process.mutate(plan.id)}>
              {process.isPending ? <Spinner /> : <PlayIcon strokeWidth={ICON_STROKE} />}
              Start processing
            </Button>
          )}
          {status === "FAILED" && (
            <Button variant="outline" disabled={process.isPending} onClick={() => process.mutate(plan.id)}>
              {process.isPending ? <Spinner /> : <RotateCcwIcon strokeWidth={ICON_STROKE} />}
              Retry
            </Button>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label={`More actions for ${plan.original_filename}`}>
                <MoreHorizontalIcon strokeWidth={ICON_STROKE} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {plan.download_url && (
                <DropdownMenuItem asChild>
                  <a href={plan.download_url} rel="noreferrer" target="_blank">
                    <DownloadIcon strokeWidth={ICON_STROKE} />
                    Download original
                  </a>
                </DropdownMenuItem>
              )}
              <DropdownMenuItem variant="destructive" onSelect={() => setConfirming(true)}>
                <Trash2Icon strokeWidth={ICON_STROKE} />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {plan.warnings.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1 sm:pl-23">
          {plan.warnings.map((w) => (
            <li key={w} className="flex items-start gap-1.5 text-ui text-warning">
              <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} aria-hidden />
              {w}
            </li>
          ))}
        </ul>
      )}

      {job && (status === "PROCESSING" || status === "FAILED" || (status === "PENDING" && isRunning(job))) && (
        <div className="mt-3 sm:pl-23">
          <ProcessingTimeline job={job} now={polledAt} />
        </div>
      )}

      {job && status === "COMPLETED" && job.stages.length > 0 && (
        <details className="group mt-2 sm:pl-23">
          <summary className="w-fit cursor-pointer text-micro text-muted-foreground hover:text-foreground">
            {job.stages.length} stages run{degraded > 0 && `, ${degraded} degraded`}
          </summary>
          <div className="mt-3">
            <ProcessingTimeline job={job} now={polledAt} />
          </div>
        </details>
      )}

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Delete this floor plan?"
        description={
          <>
            <span className="font-medium text-foreground">{plan.original_filename}</span>, its model and every version of it will be permanently deleted.
          </>
        }
        confirmLabel="Delete floor plan"
        onConfirm={() => remove.mutateAsync(plan.id)}
      />
    </li>
  );
}

export function FloorplanList({ projectId }: { projectId: string }) {
  const { data, error, isPending, refetch } = useFloorplans(projectId);
  if (isPending) return <SkeletonList rows={3} rowClassName="h-16" label="Loading floor plans" />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (!data.length) return <EmptyState icon={FileImageIcon} title="No floor plans yet" description="Upload a drawing above and it will appear here as it is processed." />;
  return (
    <ul aria-label="Floor plans" className="divide-y">
      {data.map((plan) => (
        <FloorplanRow key={plan.id} plan={plan} />
      ))}
    </ul>
  );
}
