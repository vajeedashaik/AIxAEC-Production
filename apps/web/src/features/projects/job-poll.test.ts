import { describe, expect, it } from "vitest";

import { STAGE_NAMES, type Job } from "@/contracts";

import { isRunning, isTakingLong, pollInterval, stageRows } from "./job-poll";

const T0 = Date.parse("2026-11-01T10:00:00.000Z");
const job = (over: Partial<Job> = {}): Job => ({
  id: "j",
  floorplan_id: "f",
  status: "PROCESSING",
  attempts: 1,
  stages: [],
  error_message: null,
  created_at: new Date(T0).toISOString(),
  started_at: new Date(T0).toISOString(),
  finished_at: null,
  ...over,
});
const report = (name: Job["stages"][number]["name"], status: Job["stages"][number]["status"] = "ok") => ({ name, status, duration_ms: 100, error: null, detail: {} });

describe("pollInterval", () => {
  it("polls every 2 s for the first minute", () => {
    expect(pollInterval(job(), T0)).toBe(2000);
    expect(pollInterval(job(), T0 + 59_999)).toBe(2000);
  });
  it("backs off to 6 s at 60 s", () => {
    expect(pollInterval(job(), T0 + 60_000)).toBe(6000);
    expect(pollInterval(job(), T0 + 30 * 60_000)).toBe(6000);
  });
  it("measures a queued job from when it was created", () => {
    expect(pollInterval(job({ status: "PENDING", started_at: null }), T0 + 61_000)).toBe(6000);
  });
  it("stops for finished jobs and when there is no job", () => {
    expect(pollInterval(job({ status: "COMPLETED" }), T0)).toBe(false);
    expect(pollInterval(job({ status: "FAILED" }), T0)).toBe(false);
    expect(pollInterval(undefined, T0)).toBe(false);
  });
});

describe("isTakingLong", () => {
  it("warns at 10 minutes, only while the job is live", () => {
    expect(isTakingLong(job(), T0 + 10 * 60_000 - 1)).toBe(false);
    expect(isTakingLong(job(), T0 + 10 * 60_000)).toBe(true);
    expect(isTakingLong(job({ status: "COMPLETED" }), T0 + 60 * 60_000)).toBe(false);
  });
});

describe("isRunning", () => {
  it("counts PROCESSING and a started PENDING job, not a fresh one", () => {
    expect(isRunning(job())).toBe(true);
    expect(isRunning(job({ status: "PENDING" }))).toBe(true);
    expect(isRunning(job({ status: "PENDING", started_at: null }))).toBe(false);
  });
});

describe("stageRows", () => {
  it("always lists all 8 stages in pipeline order", () => {
    expect(stageRows(job({ stages: [report("ocr")] })).map((r) => r.name)).toEqual([...STAGE_NAMES]);
  });
  it("marks the first unreported stage of a running job active", () => {
    const rows = stageRows(job({ stages: [report("preprocess"), report("wall_detection", "degraded")] }));
    expect(rows.slice(0, 4).map((r) => r.state)).toEqual(["done", "degraded", "active", "waiting"]);
  });
  it("shows no active stage once the job has failed", () => {
    const rows = stageRows(job({ status: "FAILED", stages: [report("preprocess", "failed")] }));
    expect(rows[0].state).toBe("failed");
    expect(rows.some((r) => r.state === "active")).toBe(false);
  });
});
