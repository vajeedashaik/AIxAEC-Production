// Typed client for every public endpoint in phases/shared/CONTRACTS.md §8.
import type {
  Artifact,
  CommandRequest,
  CommandResponse,
  ErrorEnvelope,
  FloorPlan,
  History,
  Job,
  Me,
  ModelEnvelope,
  Project,
  ProjectCreate,
  ProjectPage,
  ProjectUpdate,
} from "@/contracts";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const MAX_RETRY_AFTER_S = 30;

/** Clerk's `useAuth().getToken` fits this shape. */
export type GetToken = (options?: { skipCache?: boolean }) => Promise<string | null>;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> = {},
    readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const FALLBACK_CODE: Record<number, string> = {
  401: "unauthorized",
  403: "forbidden",
  404: "not_found",
  409: "conflict",
  413: "payload_too_large",
  415: "unsupported_media_type",
  422: "validation_error",
  429: "rate_limited",
  502: "upstream_unavailable",
  503: "upstream_unavailable",
};

export function parseError(status: number, body: unknown, retryAfter?: number): ApiError {
  const err = (body as Partial<ErrorEnvelope> | null)?.error;
  const code = typeof err?.code === "string" ? err.code : (FALLBACK_CODE[status] ?? "internal_error");
  const message = err?.message ?? `Request failed (${status})`;
  return new ApiError(status, code, message, (err?.details as Record<string, unknown>) ?? {}, retryAfter);
}

function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(0, seconds);
  const date = Date.parse(value);
  return Number.isNaN(date) ? undefined : Math.max(0, (date - Date.now()) / 1000);
}

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => (clearTimeout(t), reject(signal.reason)), { once: true });
  });

type Query = Record<string, string | number | boolean | null | undefined>;
type RawResponse = { status: number; body: unknown; retryAfter?: number };
type Send = (token: string | null) => Promise<RawResponse>;

export interface UploadOptions {
  process?: boolean;
  onProgress?: (fraction: number) => void;
  signal?: AbortSignal;
}

export interface VoiceOptions {
  expectedVersion?: number | null;
  dryRun?: boolean;
  signal?: AbortSignal;
}

export function createApiClient({ getToken, baseUrl = API_URL }: { getToken: GetToken; baseUrl?: string }) {
  const url = (path: string, query?: Query) => {
    const u = new URL(baseUrl + path);
    for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined && v !== null) u.searchParams.set(k, String(v));
    return u.toString();
  };

  /** Runs `send` with auth; retries once after a token refresh on 401 and once after Retry-After on 429. */
  async function run<T>(send: Send, signal?: AbortSignal): Promise<T> {
    await globalThis.__AEC_MOCK_READY__; // MSW mock mode only (src/mocks/MockProvider.tsx)
    let res = await send(await getToken());
    if (res.status === 401) res = await send(await getToken({ skipCache: true }));
    if (res.status === 429 && res.retryAfter !== undefined && res.retryAfter <= MAX_RETRY_AFTER_S) {
      await sleep(res.retryAfter * 1000, signal);
      res = await send(await getToken());
    }
    if (res.status >= 200 && res.status < 300) return res.body as T;
    throw parseError(res.status, res.body, res.retryAfter);
  }

  function viaFetch(method: string, path: string, opts: { query?: Query; json?: unknown; form?: FormData; signal?: AbortSignal } = {}): Send {
    return async (token) => {
      const headers: Record<string, string> = { Accept: "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      if (opts.json !== undefined) headers["Content-Type"] = "application/json";
      const r = await fetch(url(path, opts.query), {
        method,
        headers,
        body: opts.form ?? (opts.json !== undefined ? JSON.stringify(opts.json) : undefined),
        signal: opts.signal,
      });
      const text = r.status === 204 ? "" : await r.text();
      let body: unknown = undefined;
      try {
        body = text ? JSON.parse(text) : undefined;
      } catch {
        body = undefined;
      }
      return { status: r.status, body, retryAfter: parseRetryAfter(r.headers.get("Retry-After")) };
    };
  }

  function viaXhr(path: string, form: FormData, opts: UploadOptions, query?: Query): Send {
    return (token) =>
      new Promise<RawResponse>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", url(path, query));
        xhr.setRequestHeader("Accept", "application/json");
        if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        xhr.upload.onprogress = (e) => e.lengthComputable && opts.onProgress?.(e.loaded / e.total);
        xhr.onload = () => {
          let body: unknown = undefined;
          try {
            body = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
          } catch {
            body = undefined;
          }
          if (xhr.status >= 200 && xhr.status < 300) opts.onProgress?.(1);
          resolve({ status: xhr.status, body, retryAfter: parseRetryAfter(xhr.getResponseHeader("Retry-After")) });
        };
        xhr.onerror = () => reject(new ApiError(0, "network_error", "Network error during upload."));
        xhr.onabort = () => reject(new DOMException("Upload aborted", "AbortError"));
        opts.signal?.addEventListener("abort", () => xhr.abort(), { once: true });
        xhr.send(form);
      });
  }

  const get = <T>(path: string, query?: Query, signal?: AbortSignal) => run<T>(viaFetch("GET", path, { query, signal }), signal);
  const send = <T>(method: string, path: string, json?: unknown, query?: Query) => run<T>(viaFetch(method, path, { json, query }));
  const fp = (id: string) => `/v1/floorplans/${encodeURIComponent(id)}`;
  const pj = (id: string) => `/v1/projects/${encodeURIComponent(id)}`;

  return {
    healthz: () => get<{ status: string; service: string; version: string }>("/healthz"),
    me: (signal?: AbortSignal) => get<Me>("/v1/me", undefined, signal),

    listProjects: (params: { limit?: number; offset?: number } = {}, signal?: AbortSignal) =>
      get<ProjectPage>("/v1/projects", { limit: params.limit ?? 20, offset: params.offset ?? 0 }, signal),
    createProject: (body: ProjectCreate) => send<Project>("POST", "/v1/projects", body),
    getProject: (projectId: string, signal?: AbortSignal) => get<Project>(pj(projectId), undefined, signal),
    updateProject: (projectId: string, body: ProjectUpdate) => send<Project>("PATCH", pj(projectId), body),
    deleteProject: (projectId: string) => send<void>("DELETE", pj(projectId)),

    listFloorplans: (projectId: string, signal?: AbortSignal) => get<FloorPlan[]>(`${pj(projectId)}/floorplans`, undefined, signal),
    uploadFloorplan: (projectId: string, file: File | Blob, opts: UploadOptions = {}) => {
      const form = new FormData();
      form.append("file", file, file instanceof File ? file.name : "floorplan");
      const query = opts.process === false ? { process: false } : undefined;
      return run<FloorPlan>(viaXhr(`${pj(projectId)}/floorplans`, form, opts, query), opts.signal);
    },
    getFloorplan: (floorplanId: string, signal?: AbortSignal) => get<FloorPlan>(fp(floorplanId), undefined, signal),
    deleteFloorplan: (floorplanId: string) => send<void>("DELETE", fp(floorplanId)),
    processFloorplan: (floorplanId: string) => send<Job>("POST", `${fp(floorplanId)}/process`),
    getJob: (floorplanId: string, signal?: AbortSignal) => get<Job>(`${fp(floorplanId)}/job`, undefined, signal),
    getModel: (floorplanId: string, version?: number, signal?: AbortSignal) =>
      get<ModelEnvelope>(`${fp(floorplanId)}/model`, { version }, signal),
    listArtifacts: (floorplanId: string, signal?: AbortSignal) => get<Artifact[]>(`${fp(floorplanId)}/artifacts`, undefined, signal),

    interpretCommand: (floorplanId: string, body: CommandRequest) =>
      send<CommandResponse>("POST", `${fp(floorplanId)}/commands/interpret`, body),
    applyCommand: (floorplanId: string, body: CommandRequest) => send<CommandResponse>("POST", `${fp(floorplanId)}/commands`, body),
    postAudio: (floorplanId: string, audio: Blob, opts: VoiceOptions = {}) => {
      const form = new FormData();
      form.append("audio", audio, "command." + (audio.type.split("/")[1]?.split(";")[0] || "webm"));
      if (opts.expectedVersion != null) form.append("expected_version", String(opts.expectedVersion));
      if (opts.dryRun) form.append("dry_run", "true");
      return run<CommandResponse>(viaFetch("POST", `${fp(floorplanId)}/commands/voice`, { form, signal: opts.signal }), opts.signal);
    },
    undo: (floorplanId: string, expectedVersion?: number | null) =>
      send<CommandResponse>("POST", `${fp(floorplanId)}/model/undo`, undefined, { expected_version: expectedVersion }),
    redo: (floorplanId: string, expectedVersion?: number | null) =>
      send<CommandResponse>("POST", `${fp(floorplanId)}/model/redo`, undefined, { expected_version: expectedVersion }),
    getHistory: (floorplanId: string, signal?: AbortSignal) => get<History>(`${fp(floorplanId)}/history`, undefined, signal),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
