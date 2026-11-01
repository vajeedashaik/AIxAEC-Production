import { STAGE_NAMES, type Job, type JobStatus, type StageName, type StageReport } from "@/contracts";

const FAST_MS = 2_000;
const SLOW_MS = 6_000;
const SLOW_AFTER_MS = 60_000;
const LONG_AFTER_MS = 10 * 60_000;

export const isLive = (status: JobStatus | undefined) => status === "PENDING" || status === "PROCESSING";

/** A worker has the job. A fresh PENDING job has no started_at and still offers Start processing. */
export const isRunning = (job: Pick<Job, "status" | "started_at">) => job.status === "PROCESSING" || (job.status === "PENDING" && job.started_at !== null);

const elapsed = (job: Pick<Job, "created_at" | "started_at">, now: number) => now - Date.parse(job.started_at ?? job.created_at);

/** TanStack refetchInterval: 2 s, 6 s after a minute, stop once the job is finished. */
export function pollInterval(job: Job | undefined, now: number): number | false {
  if (!job || !isLive(job.status)) return false;
  return elapsed(job, now) >= SLOW_AFTER_MS ? SLOW_MS : FAST_MS;
}

export const isTakingLong = (job: Job, now: number) => isLive(job.status) && elapsed(job, now) >= LONG_AFTER_MS;

export const STAGE_LABELS: Record<StageName, string> = {
  preprocess: "Clean up image",
  wall_detection: "Find walls",
  ocr: "Read text",
  object_detection: "Find openings",
  room_detection: "Find rooms",
  calibration: "Calibrate scale",
  semantic_assembly: "Assemble model",
  artifacts: "Save artifacts",
};

export type StageState = "done" | "degraded" | "failed" | "skipped" | "active" | "waiting";
export interface StageRow {
  name: StageName;
  label: string;
  state: StageState;
  report?: StageReport;
}

const REPORTED: Record<StageReport["status"], StageState> = { ok: "done", degraded: "degraded", failed: "failed", skipped: "skipped" };

/** Always all 8 stages, in pipeline order. The first unreported stage of a running job is the active one. */
export function stageRows(job: Job): StageRow[] {
  const reports = new Map(job.stages.map((s) => [s.name, s]));
  const nextIndex = STAGE_NAMES.findIndex((n) => !reports.has(n));
  return STAGE_NAMES.map((name, i) => {
    const report = reports.get(name);
    const state: StageState = report ? REPORTED[report.status] : isRunning(job) && i === nextIndex ? "active" : "waiting";
    return { name, label: STAGE_LABELS[name], state, report };
  });
}
