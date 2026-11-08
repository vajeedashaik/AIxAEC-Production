// MSW handlers for every public endpoint (CONTRACTS.md §8), backed by the in-memory db.
import { delay, http, HttpResponse, type JsonBodyType } from "msw";

import type { CommandRequest } from "@/contracts";
import { API_URL } from "@/lib/api/client";

import { MockError, mockApi } from "./db";
import analysis from "./fixtures/analysis.apartment.json";
import layouts from "./fixtures/layouts.kitchen.json";

const V1 = `${API_URL}/v1`;
const TRANSCRIPT = "move the wall between the kitchen and the living room 300 mm left";

/** Wraps a resolver: maps MockError to the contract error envelope and adds a little latency. */
function handle(fn: (args: { request: Request; params: Record<string, string> }) => Promise<unknown> | unknown, status = 200) {
  return async ({ request, params }: { request: Request; params: Record<string, string | readonly string[] | undefined> }) => {
    await delay(process.env.NODE_ENV === "test" ? 0 : 120);
    try {
      const body = await fn({ request, params: params as Record<string, string> });
      return status === 204 ? new HttpResponse(null, { status }) : HttpResponse.json(body as JsonBodyType, { status });
    } catch (e) {
      if (e instanceof MockError)
        return HttpResponse.json({ error: { code: e.code, message: e.message, details: e.details } }, { status: e.status });
      throw e;
    }
  };
}

const json = async <T>(request: Request): Promise<T> => {
  try {
    return (await request.json()) as T;
  } catch {
    throw new MockError(422, "validation_error", "Body must be JSON.");
  }
};
const intParam = (request: Request, name: string) => {
  const v = new URL(request.url).searchParams.get(name);
  return v === null ? undefined : Number(v);
};

export const handlers = [
  http.get(`${API_URL}/healthz`, handle(() => ({ status: "ok", service: "api", version: "mock" }))),
  http.get(`${V1}/me`, handle(() => mockApi.me())),

  http.get(`${V1}/projects`, handle(({ request }) => mockApi.listProjects(Math.min(intParam(request, "limit") ?? 20, 100), intParam(request, "offset") ?? 0))),
  http.post(`${V1}/projects`, handle(async ({ request }) => mockApi.createProject(await json(request)), 201)),
  http.get(`${V1}/projects/:projectId`, handle(({ params }) => mockApi.getProject(params.projectId))),
  http.patch(`${V1}/projects/:projectId`, handle(async ({ request, params }) => mockApi.updateProject(params.projectId, await json(request)))),
  http.delete(`${V1}/projects/:projectId`, handle(({ params }) => mockApi.deleteProject(params.projectId), 204)),

  http.get(`${V1}/projects/:projectId/floorplans`, handle(({ params }) => mockApi.listFloorplans(params.projectId))),
  http.post(
    `${V1}/projects/:projectId/floorplans`,
    handle(async ({ request, params }) => {
      const file = (await request.formData()).get("file");
      if (!(file instanceof File)) throw new MockError(422, "validation_error", "Missing file.");
      return mockApi.uploadFloorplan(params.projectId, file, new URL(request.url).searchParams.get("process") !== "false");
    }, 201),
  ),

  http.get(`${V1}/floorplans/:floorplanId`, handle(({ params }) => mockApi.getFloorplan(params.floorplanId))),
  http.delete(`${V1}/floorplans/:floorplanId`, handle(({ params }) => mockApi.deleteFloorplan(params.floorplanId), 204)),
  http.post(`${V1}/floorplans/:floorplanId/process`, handle(({ params }) => mockApi.processFloorplan(params.floorplanId), 202)),
  http.get(`${V1}/floorplans/:floorplanId/job`, handle(({ params }) => mockApi.getJob(params.floorplanId))),
  http.get(`${V1}/floorplans/:floorplanId/model`, handle(({ request, params }) => mockApi.getModel(params.floorplanId, intParam(request, "version")))),
  http.get(`${V1}/floorplans/:floorplanId/artifacts`, handle(({ params }) => mockApi.listArtifacts(params.floorplanId))),

  http.post(
    `${V1}/floorplans/:floorplanId/commands/interpret`,
    handle(async ({ request, params }) => mockApi.command(params.floorplanId, await json<CommandRequest>(request), false)),
  ),
  http.post(
    `${V1}/floorplans/:floorplanId/commands`,
    handle(async ({ request, params }) => mockApi.command(params.floorplanId, await json<CommandRequest>(request), true)),
  ),
  http.post(
    `${V1}/floorplans/:floorplanId/commands/voice`,
    handle(async ({ request, params }) => {
      const form = await request.formData();
      if (!(form.get("audio") instanceof File)) throw new MockError(422, "validation_error", "Missing audio.");
      const expected = form.get("expected_version");
      const req: CommandRequest = { instruction: TRANSCRIPT, command: null, expected_version: expected ? Number(expected) : null };
      return mockApi.command(params.floorplanId, req, form.get("dry_run") !== "true", TRANSCRIPT);
    }),
  ),
  http.post(`${V1}/floorplans/:floorplanId/model/undo`, handle(({ request, params }) => mockApi.move(params.floorplanId, "UNDO", intParam(request, "expected_version")))),
  http.post(`${V1}/floorplans/:floorplanId/model/redo`, handle(({ request, params }) => mockApi.move(params.floorplanId, "REDO", intParam(request, "expected_version")))),
  http.get(`${V1}/floorplans/:floorplanId/history`, handle(({ params }) => mockApi.history(params.floorplanId))),
  http.post(`${V1}/floorplans/:floorplanId/analysis`, handle(() => analysis)),
  http.post(`${V1}/floorplans/:floorplanId/layouts`, handle(() => layouts)),
  http.post(`${V1}/floorplans/:floorplanId/ask`, handle(() => ({ status: "ANSWERED", answer: "This plan has 1 bedroom: BEDROOM.", element_ids: [], source: "rules" }))),
];
