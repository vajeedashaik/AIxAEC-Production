// In-memory backend for MSW (NEXT_PUBLIC_API_MOCKING=on). Seeded from the contract fixtures.
// Behaves plausibly, not exactly: a tiny geometry handles MOVE_WALL / RENAME_ROOM / ADD|DELETE door+window /
// SET_SCALE; other operations come back REJECTED so the UI can exercise every status.
import type {
  Artifact,
  Candidate,
  ChangeSet,
  CommandInput,
  CommandRequest,
  CommandResponse,
  EditLogEntry,
  FloorPlan,
  FloorPlanModel,
  History,
  Insights,
  Job,
  Me,
  ModelEnvelope,
  ModelSummary,
  Point,
  Project,
  RejectStage,
  Room,
  StageReport,
  Wall,
} from "@/contracts";
import { STAGE_NAMES } from "@/contracts";

import apartmentJson from "./fixtures/apartment.model.json";
import artifactsJson from "./fixtures/api/floorplans.artifacts.json";
import floorplanJson from "./fixtures/api/floorplans.get.json";
import meJson from "./fixtures/api/me.json";
import projectsJson from "./fixtures/api/projects.list.json";

export class MockError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

const STAGE_MS = 750; // 8 stages ≈ 6 s
const PENDING_MS = 400;
const now = () => new Date().toISOString();
const clone = <T>(v: T): T => structuredClone(v);
const uuid = () => crypto.randomUUID();

interface VersionRec {
  version: number;
  model: FloorPlanModel;
  origin: "PROCESSING" | "EDIT";
  parent_version: number | null;
  discarded: boolean;
  created_at: string;
  edit_id: string | null;
  changes: ChangeSet;
  summary: string;
}

interface FloorplanState {
  floorplan: FloorPlan;
  startedAt: number | null; // ms epoch when processing started; null = not processing
  versions: VersionRec[];
  head: number | null;
  edits: EditLogEntry[];
}

interface Db {
  me: Me;
  projects: Map<string, Project>;
  floorplans: Map<string, FloorplanState>;
  artifacts: Artifact[];
}

let db: Db = seed();

function seed(): Db {
  const fpFixture = clone(floorplanJson) as unknown as FloorPlan;
  const model = clone(apartmentJson) as unknown as FloorPlanModel;
  const fp: FloorplanState = {
    floorplan: fpFixture,
    startedAt: null,
    versions: [
      {
        version: 1,
        model,
        origin: "PROCESSING",
        parent_version: null,
        discarded: false,
        created_at: fpFixture.created_at,
        edit_id: null,
        changes: { added: [], modified: [], removed: [] },
        summary: "Processed upload.",
      },
    ],
    head: 1,
    edits: [],
  };
  const projects = (clone(projectsJson).items as unknown as Project[]).map((p) => [p.id, p] as const);
  return {
    me: clone(meJson) as unknown as Me,
    projects: new Map(projects),
    floorplans: new Map([[fpFixture.id, fp]]),
    artifacts: clone(artifactsJson) as unknown as Artifact[],
  };
}

/** Test helper: restore the seeded state. */
export function resetDb() {
  db = seed();
}

// ── geometry helpers ──────────────────────────────────────────────────────────────

export function polygonArea(pts: Point[]): number {
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % pts.length];
    s += a.x * b.y - b.x * a.y;
  }
  return Math.abs(s) / 2;
}

const wallLength = (w: Wall) => Math.hypot(w.end.x - w.start.x, w.end.y - w.start.y);

export function summarize(m: FloorPlanModel): ModelSummary {
  return {
    walls: m.walls.length,
    doors: m.doors.length,
    windows: m.windows.length,
    columns: m.columns.length,
    stairs: m.stairs.length,
    furniture: m.furniture.length,
    dimensions: m.dimensions.length,
    rooms: m.rooms.length,
  };
}

export function insights(m: FloorPlanModel): Insights {
  const areas = m.rooms.map((r) => polygonArea(r.polygon));
  const uses = new Map<string, number>();
  for (const r of m.rooms) for (const id of r.wall_ids) uses.set(id, (uses.get(id) ?? 0) + 1);
  const total = m.walls.reduce((s, w) => s + wallLength(w), 0);
  const exterior = m.walls.filter((w) => (uses.get(w.id) ?? 0) <= 1).reduce((s, w) => s + wallLength(w), 0);
  const totalArea = areas.reduce((a, b) => a + b, 0);
  const avg = areas.length ? totalArea / areas.length : 0;
  const order = m.rooms.map((r, i) => ({ r, a: areas[i] })).sort((x, y) => x.a - y.a);
  const ref = (o?: { r: Room; a: number }) => (o ? { id: o.r.id, label: o.r.label_text, area_px: o.a } : null);
  const byType: Record<string, number> = {};
  for (const r of m.rooms) byType[r.room_type] = (byType[r.room_type] ?? 0) + 1;
  const mpp = m.coordinate_system.mm_per_pixel;
  const r2 = (v: number) => Math.round(v * 100) / 100;
  return {
    counts: summarize(m),
    total_area_px: totalArea,
    average_room_area_px: avg,
    largest_room: ref(order.at(-1)),
    smallest_room: ref(order[0]),
    total_wall_length_px: total,
    exterior_wall_length_px: exterior,
    interior_wall_length_px: total - exterior,
    rooms_by_type: byType,
    metric: mpp
      ? {
          total_area_m2: r2(totalArea * (mpp / 1000) ** 2),
          average_room_area_m2: r2(avg * (mpp / 1000) ** 2),
          total_wall_length_m: r2((total * mpp) / 1000),
          exterior_wall_length_m: r2((exterior * mpp) / 1000),
          interior_wall_length_m: r2(((total - exterior) * mpp) / 1000),
        }
      : null,
  };
}

const same = (a: Point, b: Point) => Math.abs(a.x - b.x) < 1e-6 && Math.abs(a.y - b.y) < 1e-6;

function moveWall(m: FloorPlanModel, wallId: string, dx: number, dy: number): ChangeSet {
  const wall = m.walls.find((w) => w.id === wallId)!;
  const ends = [clone(wall.start), clone(wall.end)];
  const modified = new Set<string>();
  const shift = (p: Point) => {
    if (ends.some((e) => same(e, p))) {
      p.x += dx;
      p.y += dy;
      return true;
    }
    return false;
  };
  for (const w of m.walls) if ([shift(w.start), shift(w.end)].some(Boolean)) modified.add(w.id);
  for (const r of m.rooms) {
    if (r.polygon.map(shift).some(Boolean)) {
      r.area_px = polygonArea(r.polygon);
      modified.add(r.id);
    }
  }
  for (const o of [...m.doors, ...m.windows]) {
    if (o.wall_id === wallId) {
      o.bbox.x += dx;
      o.bbox.y += dy;
      modified.add(o.id);
    }
  }
  return { added: [], modified: [...modified], removed: [] };
}

function openingOnWall(w: Wall, position: number, widthPx: number, kind: "door" | "window") {
  const t = w.thickness_px ?? 10;
  const cx = w.start.x + (w.end.x - w.start.x) * position;
  const cy = w.start.y + (w.end.y - w.start.y) * position;
  const horizontal = Math.abs(w.end.x - w.start.x) >= Math.abs(w.end.y - w.start.y);
  const bbox = horizontal
    ? { x: cx - widthPx / 2, y: cy - t / 2, width: widthPx, height: t }
    : { x: cx - t / 2, y: cy - widthPx / 2, width: t, height: widthPx };
  const base = { id: uuid(), confidence: null, source: "USER_CONFIRMED" as const, bbox, wall_id: w.id, width_px: widthPx };
  return kind === "door" ? { ...base, swing: null } : base;
}

// ── command execution ─────────────────────────────────────────────────────────────

type Outcome =
  | { status: "APPLIED"; model: FloorPlanModel; changes: ChangeSet; command: CommandInput; summary: string }
  | { status: "CLARIFICATION"; question: string; candidates: Candidate[]; command?: CommandInput }
  | { status: "REJECTED"; stage: RejectStage; detail: string };

const reject = (stage: RejectStage, detail: string): Outcome => ({ status: "REJECTED", stage, detail });
const DIRS: Record<string, "LEFT" | "RIGHT" | "UP" | "DOWN"> = {
  left: "LEFT", west: "LEFT", right: "RIGHT", east: "RIGHT", up: "UP", north: "UP", down: "DOWN", south: "DOWN",
};

function wallCandidate(w: Wall, note = ""): Candidate {
  const vertical = Math.abs(w.end.x - w.start.x) < Math.abs(w.end.y - w.start.y);
  return {
    id: w.id,
    kind: "wall",
    label: `${vertical ? "vertical" : "horizontal"} wall, ${Math.round(wallLength(w))} px long${note}`,
    x: (w.start.x + w.end.x) / 2,
    y: (w.start.y + w.end.y) / 2,
  };
}

function roomsMentioned(text: string, m: FloorPlanModel): Room[] {
  const hits: { r: Room; at: number }[] = [];
  for (const r of m.rooms) {
    const words = [r.label_text, r.room_type.replace(/_/g, " "), r.room_type.split("_")[0]]
      .filter((w): w is string => !!w && w !== "UNKNOWN")
      .map((w) => w.toLowerCase());
    const at = Math.min(...words.map((w) => text.indexOf(w)).filter((i) => i >= 0));
    if (Number.isFinite(at)) hits.push({ r, at });
  }
  return hits.sort((a, b) => a.at - b.at).map((h) => h.r);
}

/** A rules-only stand-in for the language service: text -> structured command or a non-APPLIED outcome. */
function parseInstruction(text: string, m: FloorPlanModel): CommandInput | Outcome {
  const t = text.toLowerCase().trim();
  const rename = text.trim().match(/^(?:rename|call|label)\s+(?:the\s+)?(.+?)\s+(?:to|as)\s+['"]?(.+?)['"]?$/i);
  if (rename) {
    const rooms = roomsMentioned(rename[1].toLowerCase(), m);
    if (!rooms.length) return reject("entity_resolution", `I couldn't find a room called “${rename[1]}”.`);
    return { operation: "RENAME_ROOM", target_id: rooms[0].id, name: rename[2].slice(0, 80) };
  }
  const opening = t.match(/\b(?:delete|remove)\b.*\b(door|window)\b/);
  if (opening) {
    const kind = opening[1] as "door" | "window";
    const rooms = roomsMentioned(t, m);
    const wallIds = new Set(rooms.flatMap((r) => r.wall_ids));
    const list = kind === "door" ? m.doors : m.windows;
    const found = list.filter((o) => o.wall_id && (!rooms.length || wallIds.has(o.wall_id)));
    if (found.length === 1)
      return { operation: kind === "door" ? "DELETE_DOOR" : "DELETE_WINDOW", target_id: found[0].id };
    if (!found.length) return reject("entity_resolution", `I couldn't find that ${kind}.`);
    return {
      status: "CLARIFICATION",
      question: `Which ${kind} do you mean?`,
      command: { operation: kind === "door" ? "DELETE_DOOR" : "DELETE_WINDOW", target_query: kind } as CommandInput,
      candidates: found.map((o) => ({
        id: o.id,
        kind,
        label: `${kind} at (${Math.round(o.bbox.x)}, ${Math.round(o.bbox.y)})`,
        x: o.bbox.x + o.bbox.width / 2,
        y: o.bbox.y + o.bbox.height / 2,
      })),
    };
  }
  if (/\b(move|shift|push|nudge)\b.*\bwall\b/.test(t)) {
    const dist = t.match(/(-?\d+(?:\.\d+)?)\s*(mm|millimet(?:er|re)s?|cm|m|met(?:er|re)s?|px|pixels?)\b/);
    const dir = Object.keys(DIRS).find((d) => new RegExp(`\\b${d}\\b`).test(t));
    const rooms = roomsMentioned(t, m);
    let wall: Wall | undefined;
    if (/\bbetween\b/.test(t) && rooms.length >= 2) {
      wall = m.walls.find((w) => rooms[0].wall_ids.includes(w.id) && rooms[1].wall_ids.includes(w.id));
    }
    if (!dist || !dir) return reject("parse", "Say how far and which way, e.g. “300 mm left”.");
    const value = Number(dist[1]);
    if (!(value > 0)) return reject("schema", "The distance must be greater than zero.");
    const unit = dist[2];
    const mm = unit.startsWith("c") ? value * 10 : unit === "m" || unit.startsWith("met") ? value * 1000 : value;
    const move = { operation: "MOVE_WALL", direction: DIRS[dir], distance: unit.startsWith("p") ? { value, unit: "px" as const } : { value: mm, unit: "mm" as const } } as const;
    if (!wall) {
      const pool = rooms.length ? m.walls.filter((w) => rooms[0].wall_ids.includes(w.id)) : m.walls;
      // Like the real API: the parsed command comes back unresolved, so the UI re-sends it with the picked id.
      return { status: "CLARIFICATION", question: "Which wall do you mean?", candidates: pool.slice(0, 4).map((w) => wallCandidate(w)), command: { ...move, target_query: "wall" } as CommandInput };
    }
    return { ...move, target_id: wall.id };
  }
  return reject("parse", "I couldn't turn that into an edit. Try “move the wall between the kitchen and the living room 300 mm left”.");
}

function execute(base: FloorPlanModel, req: CommandRequest): Outcome {
  const parsed = req.instruction ? parseInstruction(req.instruction, base) : (req.command as CommandInput | undefined);
  if (!parsed || typeof parsed !== "object") return reject("schema", "Command must be an object.");
  if ("status" in parsed) return parsed;
  const cmd = clone(parsed);
  const m = clone(base);
  m.id = uuid();
  const mpp = m.coordinate_system.mm_per_pixel;
  const toPx = (d: { value: number; unit: "mm" | "px" }) => (d.unit === "px" ? d.value : mpp ? d.value / mpp : null);
  const fmt = (d: { value: number; unit: string }) => `${d.value} ${d.unit}`;
  const target = "target_id" in cmd ? cmd.target_id : undefined;
  if ("target_query" in cmd && cmd.target_query && !target)
    return reject("entity_resolution", "The mock backend only resolves target_id; use an instruction or pick an element.");

  switch (cmd.operation) {
    case "MOVE_WALL": {
      const wall = m.walls.find((w) => w.id === target);
      if (!wall) return reject("entity_resolution", "That wall no longer exists.");
      const px = toPx(cmd.distance);
      if (px === null) return reject("semantic_validation", "Set a scale first to use millimetres.");
      const vertical = Math.abs(wall.end.x - wall.start.x) < Math.abs(wall.end.y - wall.start.y);
      const horizontalMove = cmd.direction === "LEFT" || cmd.direction === "RIGHT";
      if (vertical !== horizontalMove) return reject("semantic_validation", "A wall can only move perpendicular to its length.");
      const sign = cmd.direction === "LEFT" || cmd.direction === "UP" ? -1 : 1;
      const changes = moveWall(m, wall.id, horizontalMove ? sign * px : 0, horizontalMove ? 0 : sign * px);
      const out = [...m.walls.flatMap((w) => [w.start, w.end]), ...m.rooms.flatMap((r) => r.polygon)].some((p) => p.x < 0 || p.y < 0);
      if (out) return reject("constraints", "That would push the plan outside the drawing.");
      const resized = m.rooms.filter((r) => changes.modified.includes(r.id) && r.area_px !== base.rooms.find((b) => b.id === r.id)?.area_px);
      return { status: "APPLIED", model: m, changes, command: cmd, summary: `Moved wall ${fmt(cmd.distance)} ${cmd.direction.toLowerCase()}; ${resized.length} rooms resized.` };
    }
    case "RENAME_ROOM": {
      const room = m.rooms.find((r) => r.id === target);
      if (!room) return reject("entity_resolution", "That room no longer exists.");
      room.label_text = cmd.name;
      if (cmd.room_type) Object.assign(room, { room_type: cmd.room_type, room_type_source: "USER_CONFIRMED", room_type_confidence: 1 });
      return { status: "APPLIED", model: m, changes: { added: [], modified: [room.id], removed: [] }, command: cmd, summary: `Renamed room to “${cmd.name}”.` };
    }
    case "DELETE_DOOR":
    case "DELETE_WINDOW": {
      const door = cmd.operation === "DELETE_DOOR";
      const list: { id: string }[] = door ? m.doors : m.windows;
      const index = list.findIndex((o) => o.id === target);
      if (index < 0) return reject("entity_resolution", "That opening no longer exists.");
      list.splice(index, 1);
      return { status: "APPLIED", model: m, changes: { added: [], modified: [], removed: [target!] }, command: cmd, summary: `Deleted ${door ? "door" : "window"}.` };
    }
    case "ADD_DOOR":
    case "ADD_WINDOW": {
      const wall = m.walls.find((w) => w.id === target);
      if (!wall) return reject("entity_resolution", "That wall no longer exists.");
      const kind = cmd.operation === "ADD_DOOR" ? "door" : "window";
      const width = cmd.width ? toPx(cmd.width) : kind === "door" ? 90 : 120;
      if (width === null) return reject("semantic_validation", "Set a scale first to use millimetres.");
      if (width >= wallLength(wall)) return reject("constraints", `The ${kind} is wider than the wall.`);
      const o = openingOnWall(wall, cmd.position ?? 0.5, width, kind);
      if (kind === "door") m.doors.push(o as FloorPlanModel["doors"][number]);
      else m.windows.push(o as FloorPlanModel["windows"][number]);
      return { status: "APPLIED", model: m, changes: { added: [o.id], modified: [], removed: [] }, command: cmd, summary: `Added a ${kind}.` };
    }
    case "SET_SCALE": {
      const wall = m.walls.find((w) => w.id === target);
      if (!wall) return reject("entity_resolution", "That wall no longer exists.");
      Object.assign(m.coordinate_system, { mm_per_pixel: cmd.length_mm / wallLength(wall), calibration_source: "MANUAL", calibration_confidence: 1 });
      return { status: "APPLIED", model: m, changes: { added: [], modified: [], removed: [] }, command: cmd, summary: `Scale set: ${(cmd.length_mm / wallLength(wall)).toFixed(2)} mm per pixel.` };
    }
    default:
      return reject("geometry", `${cmd.operation} isn't supported by the mock backend. It works against the real geometry service.`);
  }
}

// ── processing timeline ───────────────────────────────────────────────────────────

function tick(s: FloorplanState) {
  if (s.startedAt === null) return;
  const elapsed = Date.now() - s.startedAt;
  const job = s.floorplan.latest_job!;
  const done = Math.max(0, Math.min(STAGE_NAMES.length, Math.floor((elapsed - PENDING_MS) / STAGE_MS)));
  job.stages = STAGE_NAMES.slice(0, done).map(
    (name, i): StageReport => ({ name, status: name === "ocr" ? "degraded" : "ok", duration_ms: STAGE_MS - 40 + i * 7, error: null, detail: {} }),
  );
  if (elapsed < PENDING_MS) return;
  if (job.status === "PENDING") Object.assign(job, { status: "PROCESSING", attempts: 1, started_at: now() });
  s.floorplan.status = job.status;
  if (done < STAGE_NAMES.length) return;
  const model = clone(apartmentJson) as unknown as FloorPlanModel;
  model.id = uuid();
  model.floorplan_id = s.floorplan.id;
  Object.assign(job, { status: "COMPLETED", finished_at: now() });
  s.versions = [{ version: 1, model, origin: "PROCESSING", parent_version: null, discarded: false, created_at: now(), edit_id: null, changes: { added: [], modified: [], removed: [] }, summary: "Processed upload." }];
  s.head = 1;
  s.edits = [];
  Object.assign(s.floorplan, { status: "COMPLETED", current_model_version: 1, warnings: ["OCR ran in degraded mode (mock)."] });
  s.startedAt = null;
}

// ── public API (one function per endpoint) ────────────────────────────────────────

const notFound = () => new MockError(404, "not_found", "Not found.");

function fpState(id: string): FloorplanState {
  const s = db.floorplans.get(id);
  if (!s) throw notFound();
  tick(s);
  return s;
}

function headRec(s: FloorplanState): VersionRec {
  const rec = s.versions.find((v) => v.version === s.head);
  if (!rec) throw new MockError(409, "model_not_ready", "The plan is still being processed.");
  return rec;
}

function checkVersion(s: FloorplanState, expected: number | null | undefined) {
  if (expected != null && expected !== s.head)
    throw new MockError(409, "stale_model", "The plan changed since you loaded it.", { head_version: s.head });
}

function newJob(floorplanId: string): Job {
  return { id: uuid(), floorplan_id: floorplanId, status: "PENDING", attempts: 0, stages: [], error_message: null, created_at: now(), started_at: null, finished_at: null };
}

export const mockApi = {
  me: () => db.me,

  listProjects(limit = 20, offset = 0) {
    const all = [...db.projects.values()].sort((a, b) => b.created_at.localeCompare(a.created_at));
    return { items: all.slice(offset, offset + limit), total: all.length, limit, offset };
  },
  createProject(body: { name?: string; description?: string | null }): Project {
    if (!body.name?.trim() || body.name.length > 200) throw new MockError(422, "validation_error", "Name is required (max 200 characters).");
    const p: Project = { id: uuid(), name: body.name, description: body.description ?? null, floorplan_count: 0, thumbnail_url: null, created_at: now(), updated_at: now() };
    db.projects.set(p.id, p);
    return p;
  },
  getProject(id: string) {
    const p = db.projects.get(id);
    if (!p) throw notFound();
    return { ...p, floorplan_count: [...db.floorplans.values()].filter((f) => f.floorplan.project_id === id).length };
  },
  updateProject(id: string, body: { name?: string | null; description?: string | null }) {
    const p = db.projects.get(id);
    if (!p) throw notFound();
    if (body.name !== undefined && (!body.name || body.name.length > 200)) throw new MockError(422, "validation_error", "Name must be 1-200 characters.");
    Object.assign(p, { ...(body.name ? { name: body.name } : {}), ...("description" in body ? { description: body.description } : {}), updated_at: now() });
    return this.getProject(id);
  },
  deleteProject(id: string) {
    if (!db.projects.delete(id)) throw notFound();
    for (const [fid, s] of db.floorplans) if (s.floorplan.project_id === id) db.floorplans.delete(fid);
  },

  listFloorplans(projectId: string) {
    this.getProject(projectId);
    return [...db.floorplans.values()]
      .filter((s) => s.floorplan.project_id === projectId)
      .map((s) => (tick(s), s.floorplan))
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
  },
  uploadFloorplan(projectId: string, file: File, process = true): FloorPlan {
    this.getProject(projectId);
    if (!["image/png", "image/jpeg", "application/pdf"].includes(file.type))
      throw new MockError(415, "unsupported_media_type", "Upload a PNG, JPG or PDF.");
    if (file.size > 26_214_400) throw new MockError(413, "payload_too_large", "The file is larger than 25 MB.");
    const id = uuid();
    const version = [...db.floorplans.values()].filter((s) => s.floorplan.project_id === projectId).length + 1;
    const floorplan: FloorPlan = {
      id, project_id: projectId, version, original_filename: file.name, content_type: file.type, size_bytes: file.size,
      status: "PENDING", current_model_version: null, download_url: null, latest_job: newJob(id), warnings: [], created_at: now(),
    };
    db.floorplans.set(id, { floorplan, startedAt: process ? Date.now() : null, versions: [], head: null, edits: [] });
    return clone(floorplan);
  },
  getFloorplan: (id: string) => clone(fpState(id).floorplan),
  deleteFloorplan(id: string) {
    if (!db.floorplans.delete(id)) throw notFound();
  },
  processFloorplan(id: string): Job {
    const s = fpState(id);
    if (s.startedAt !== null) throw new MockError(409, "already_processing", "This plan is already being processed.");
    s.floorplan.latest_job = newJob(id);
    s.floorplan.status = "PENDING";
    s.startedAt = Date.now();
    return clone(s.floorplan.latest_job);
  },
  getJob(id: string): Job {
    const job = fpState(id).floorplan.latest_job;
    if (!job) throw notFound();
    return clone(job);
  },
  getModel(id: string, version?: number): ModelEnvelope {
    const s = fpState(id);
    const rec = version ? s.versions.find((v) => v.version === version) : headRec(s);
    if (!rec) throw version ? notFound() : new MockError(409, "model_not_ready", "The plan is still being processed.");
    return { floorplan_id: id, version: rec.version, model: clone(rec.model), summary: summarize(rec.model), insights: insights(rec.model) };
  },
  listArtifacts(id: string): Artifact[] {
    const s = fpState(id);
    return s.floorplan.status === "COMPLETED" ? clone(db.artifacts).map((a) => ({ ...a, job_id: s.floorplan.latest_job?.id ?? a.job_id })) : [];
  },

  command(id: string, req: CommandRequest, persist: boolean, transcript: string | null = null): CommandResponse {
    if ((req.instruction == null) === (req.command == null))
      throw new MockError(422, "validation_error", "Send exactly one of instruction or command.");
    const s = fpState(id);
    const base = headRec(s);
    checkVersion(s, req.expected_version);
    const out = execute(base.model, req);
    const empty = { model: null, changes: null, command: null, summary: null, question: null, candidates: [], stage: null, detail: null, transcript, edit_id: null };
    let res: CommandResponse;
    if (out.status === "APPLIED") {
      res = { ...empty, status: persist ? "APPLIED" : "PREVIEW", version: base.version, model: out.model, changes: out.changes, command: out.command as CommandResponse["command"], summary: out.summary };
    } else if (out.status === "CLARIFICATION") {
      res = { ...empty, status: "CLARIFICATION", version: base.version, question: out.question, candidates: out.candidates, command: (out.command ?? null) as CommandResponse["command"] };
    } else {
      res = { ...empty, status: "REJECTED", version: base.version, stage: out.stage, detail: out.detail };
    }
    if (!persist) return res;

    const editId = uuid();
    const created = now();
    let resultVersion: number | null = null;
    if (out.status === "APPLIED") {
      for (const v of s.versions) if (v.version > base.version) v.discarded = true;
      resultVersion = Math.max(...s.versions.map((v) => v.version)) + 1;
      s.versions.push({ version: resultVersion, model: clone(out.model), origin: "EDIT", parent_version: base.version, discarded: false, created_at: created, edit_id: editId, changes: out.changes, summary: out.summary });
      s.head = resultVersion;
      s.floorplan.current_model_version = resultVersion;
      res.version = resultVersion;
    }
    s.edits.push({
      id: editId, instruction: req.instruction ?? transcript, operation: out.status === "APPLIED" ? out.command.operation : null,
      status: out.status, stage: out.status === "REJECTED" ? out.stage : null, error: out.status === "REJECTED" ? out.detail : null,
      parent_version: base.version, result_version: resultVersion, created_at: created,
    });
    res.edit_id = editId;
    return res;
  },

  move(id: string, direction: "UNDO" | "REDO", expected?: number | null): CommandResponse {
    const s = fpState(id);
    const cur = headRec(s);
    checkVersion(s, expected);
    const target =
      direction === "UNDO"
        ? s.versions.find((v) => v.version === cur.parent_version)
        : s.versions.find((v) => v.parent_version === cur.version && !v.discarded);
    if (!target) throw new MockError(409, "conflict", direction === "UNDO" ? "Nothing to undo." : "Nothing to redo.");
    const undone = direction === "UNDO" ? cur : target;
    s.head = target.version;
    s.floorplan.current_model_version = target.version;
    const editId = uuid();
    s.edits.push({ id: editId, instruction: null, operation: null, status: direction, stage: null, error: null, parent_version: cur.version, result_version: target.version, created_at: now() });
    return {
      status: "APPLIED", version: target.version, model: clone(target.model), changes: undone.changes, command: null,
      summary: `${direction === "UNDO" ? "Undid" : "Redid"}: ${undone.summary}`, question: null, candidates: [], stage: null,
      detail: null, transcript: null, edit_id: editId,
    };
  },

  history(id: string): History {
    const s = fpState(id);
    const head = s.versions.find((v) => v.version === s.head);
    return {
      head_version: s.head,
      can_undo: !!head?.parent_version,
      can_redo: !!head && s.versions.some((v) => v.parent_version === head.version && !v.discarded),
      versions: s.versions.map((v) => ({ version: v.version, origin: v.origin, parent_version: v.parent_version, discarded: v.discarded, is_head: v.version === s.head, created_at: v.created_at, edit_id: v.edit_id })),
      edits: [...s.edits].reverse(),
    };
  },
};
