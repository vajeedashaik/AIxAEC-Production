// @vitest-environment node
// Node env: jsdom's File/FormData are not understood by undici's multipart parser that MSW uses.
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import apartment from "@/mocks/fixtures/apartment.model.json";
import { server } from "@/mocks/node";

import { API_URL, ApiError, createApiClient } from "./client";

const FP = apartment.floorplan_id;
const api = createApiClient({ getToken: async () => "test-token" });

/** Minimal fetch-backed XMLHttpRequest so the upload path runs through MSW in Node (reports one progress event). */
class FetchXhr {
  status = 0;
  responseText = "";
  upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {};
  onload?: () => void;
  onerror?: () => void;
  onabort?: () => void;
  private method = "GET";
  private url = "";
  private headers: Record<string, string> = {};
  private responseHeaders = new Headers();
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v;
  }
  getResponseHeader(k: string) {
    return this.responseHeaders.get(k);
  }
  abort() {
    this.onabort?.();
  }
  send(body: FormData) {
    this.upload.onprogress?.({ lengthComputable: true, loaded: 1, total: 2 });
    fetch(this.url, { method: this.method, headers: this.headers, body }).then(
      async (r) => {
        this.status = r.status;
        this.responseHeaders = r.headers;
        this.responseText = await r.text();
        this.onload?.();
      },
      () => this.onerror?.(),
    );
  }
}

beforeAll(() => vi.stubGlobal("XMLHttpRequest", FetchXhr));
afterEach(() => vi.useRealTimers());

describe("api client against MSW mocks", () => {
  it("lists projects and parses the error envelope", async () => {
    const page = await api.listProjects();
    expect(page.total).toBe(2);
    expect(page.items[0].name).toBeTruthy();

    const err = await api.getProject("00000000-0000-4000-8000-000000000000").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: "not_found" });
  });

  it("runs interpret → apply → undo → redo with versions and stale checks", async () => {
    const { version, model } = await api.getModel(FP);
    expect(version).toBe(1);
    expect(model.rooms).toHaveLength(5);

    const instruction = "move the wall between the kitchen and the living room 300 mm left";
    const preview = await api.interpretCommand(FP, { instruction, expected_version: 1 });
    expect(preview).toMatchObject({ status: "PREVIEW", version: 1 });
    expect(preview.changes?.modified.length).toBeGreaterThan(0);
    expect((await api.getHistory(FP)).head_version).toBe(1); // preview is not persisted

    const applied = await api.applyCommand(FP, { instruction, expected_version: 1 });
    expect(applied).toMatchObject({ status: "APPLIED", version: 2 });
    expect(applied.command?.operation).toBe("MOVE_WALL");

    const stale = await api.applyCommand(FP, { instruction, expected_version: 1 }).catch((e: unknown) => e);
    expect(stale).toMatchObject({ status: 409, code: "stale_model" });

    expect(await api.undo(FP, 2)).toMatchObject({ status: "APPLIED", version: 1 });
    expect(await api.redo(FP, 1)).toMatchObject({ status: "APPLIED", version: 2 });
    const history = await api.getHistory(FP);
    expect(history).toMatchObject({ head_version: 2, can_undo: true, can_redo: false });
    expect(history.edits.map((e) => e.status)).toEqual(["REDO", "UNDO", "APPLIED"]);
  });

  it("returns CLARIFICATION and REJECTED outcomes", async () => {
    const clarify = await api.interpretCommand(FP, { instruction: "move the kitchen wall 30 cm left" });
    expect(clarify.status).toBe("CLARIFICATION");
    expect(clarify.candidates.length).toBeGreaterThanOrEqual(2);

    const nonsense = await api.applyCommand(FP, { instruction: "make it nicer" });
    expect(nonsense).toMatchObject({ status: "REJECTED", stage: "parse" });
  });

  it("retries once with a refreshed token on 401", async () => {
    server.use(
      http.get(`${API_URL}/v1/me`, ({ request }) =>
        request.headers.get("Authorization") === "Bearer fresh"
          ? HttpResponse.json({ id: "x" })
          : HttpResponse.json({ error: { code: "unauthorized" } }, { status: 401 }),
      ),
    );
    const getToken = vi.fn(async (o?: { skipCache?: boolean }) => (o?.skipCache ? "fresh" : "stale"));
    await expect(createApiClient({ getToken }).me()).resolves.toMatchObject({ id: "x" });
    expect(getToken).toHaveBeenLastCalledWith({ skipCache: true });
  });

  it("honours Retry-After on 429", async () => {
    let calls = 0;
    server.use(
      http.get(`${API_URL}/v1/me`, () =>
        ++calls === 1
          ? HttpResponse.json({ error: { code: "rate_limited" } }, { status: 429, headers: { "Retry-After": "0" } })
          : HttpResponse.json({ id: "y" }),
      ),
    );
    await expect(api.me()).resolves.toMatchObject({ id: "y" });
    expect(calls).toBe(2);
  });

  it("uploads with progress over XHR and processing advances to COMPLETED", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    const projectId = (await api.listProjects()).items[0].id;
    const progress: number[] = [];
    const file = new File([new Uint8Array(2048)], "plan.png", { type: "image/png" });
    const fp = await api.uploadFloorplan(projectId, file, { onProgress: (f) => progress.push(f) });
    expect(fp).toMatchObject({ status: "PENDING", original_filename: "plan.png" });
    expect(progress.at(-1)).toBe(1);

    await expect(api.getModel(fp.id)).rejects.toMatchObject({ code: "model_not_ready" });
    vi.setSystemTime(Date.now() + 3000);
    expect((await api.getJob(fp.id)).status).toBe("PROCESSING");
    vi.setSystemTime(Date.now() + 5000);
    const job = await api.getJob(fp.id);
    expect(job.status).toBe("COMPLETED");
    expect(job.stages).toHaveLength(8);
    expect((await api.getModel(fp.id)).model.floorplan_id).toBe(fp.id);
  });

  it("rejects unsupported uploads with 415", async () => {
    const projectId = (await api.listProjects()).items[0].id;
    const err = await api.uploadFloorplan(projectId, new File(["x"], "a.txt", { type: "text/plain" })).catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 415, code: "unsupported_media_type" });
  });

  it("posts audio and returns the transcript", async () => {
    const res = await api.postAudio(FP, new Blob(["x"], { type: "audio/webm" }), { dryRun: true, expectedVersion: 1 });
    expect(res.status).toBe("PREVIEW");
    expect(res.transcript).toContain("kitchen");
  });
});
