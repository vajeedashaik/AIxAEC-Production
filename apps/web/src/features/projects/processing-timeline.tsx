"use client";

import { AlertTriangleIcon, CheckIcon, CircleDashedIcon, MinusIcon, XIcon } from "lucide-react";
import type { ReactNode } from "react";

import { ICON_STROKE, Spinner } from "@/components/composites";
import type { Job } from "@/contracts";
import { formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

import { isTakingLong, stageRows, type StageState } from "./job-poll";

const STATE: Record<StageState, { icon: ReactNode; text: string; bar: string; word: string }> = {
  done: { icon: <CheckIcon className="size-3.5 text-success" strokeWidth={2} aria-hidden />, text: "text-foreground", bar: "bg-success", word: "done" },
  degraded: { icon: <AlertTriangleIcon className="size-3.5 text-warning" strokeWidth={2} aria-hidden />, text: "text-foreground", bar: "bg-warning", word: "degraded" },
  failed: { icon: <XIcon className="size-3.5 text-danger" strokeWidth={2} aria-hidden />, text: "text-foreground", bar: "bg-danger", word: "failed" },
  skipped: { icon: <MinusIcon className="size-3.5 text-muted-foreground" strokeWidth={2} aria-hidden />, text: "text-muted-foreground", bar: "bg-border-strong", word: "skipped" },
  active: { icon: <Spinner className="size-3.5 text-info" />, text: "text-foreground font-medium", bar: "bg-info animate-pulse motion-reduce:animate-none", word: "running" },
  waiting: { icon: <CircleDashedIcon className="size-3.5 text-muted-foreground" strokeWidth={ICON_STROKE} aria-hidden />, text: "text-muted-foreground", bar: "bg-border", word: "waiting" },
};

/** The 8 pipeline stages as one continuous strip: a bar per stage, its name and its true duration. */
export function ProcessingTimeline({ job, now }: { job: Job; now: number }) {
  const rows = stageRows(job);
  return (
    <div className="flex flex-col gap-3">
      <ol aria-label="Processing stages" className="grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-4 xl:grid-cols-8">
        {rows.map(({ name, label, state, report }) => {
          const s = STATE[state];
          return (
            <li key={name} aria-current={state === "active" ? "step" : undefined} className="min-w-0">
              <div aria-hidden className={cn("mb-2 h-1 rounded-full", s.bar)} />
              <div className={cn("flex items-center gap-1.5 text-ui", s.text)}>
                {s.icon}
                <span className="truncate">{label}</span>
                <span className="sr-only">: {s.word}</span>
              </div>
              <p className="numeric mt-0.5 pl-5 text-micro text-muted-foreground">
                {report ? formatDuration(report.duration_ms) : state === "active" ? "running" : "–"}
                {state === "degraded" && " · degraded"}
              </p>
              {report?.error && <p className="mt-1 pl-5 text-micro text-danger">{report.error}</p>}
            </li>
          );
        })}
      </ol>
      {job.error_message && (
        <p role="alert" className="text-ui text-danger">
          {job.error_message}
        </p>
      )}
      {isTakingLong(job, now) && (
        <p role="status" className="flex items-center gap-1.5 text-ui text-warning">
          <AlertTriangleIcon className="size-3.5" strokeWidth={2} aria-hidden />
          This is taking longer than usual. It will keep running; you can leave this page.
        </p>
      )}
    </div>
  );
}
