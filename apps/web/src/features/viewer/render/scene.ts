import { roomFillVar, type BBox, type Door, type FloorPlanModel, type RoomType, type Stair } from "@/contracts";

import { bboxPolygon, boundsOf, polygonArea, polygonCentroid, round2, validBBox, validRoom, validWall, wallPolygon } from "./geometry";
import type { CanvasToken, LayerId, Primitive, Pt, Scene } from "./types";
import { formatArea } from "./units";

export interface BuildSceneOptions {
  /** Layers to include; all when omitted. */
  layers?: Partial<Record<LayerId, boolean>>;
}

/** "var(--canvas-x)" -> "canvas-x" */
const roomFillToken = (type: RoomType) => roomFillVar(type).slice(6, -1) as CanvasToken;

export const roomTypeName = (type: string) => type.charAt(0) + type.slice(1).toLowerCase().replace(/_/g, " ");
export const roomName = (r: { label_text: string | null; room_type: string }) =>
  r.label_text || (r.room_type === "UNKNOWN" ? "Room" : roomTypeName(r.room_type));

function doorPrimitives(d: Door): Primitive[] {
  const base = { elementId: d.id, kind: "door", layer: "openings" } as const;
  const { x, y, width, height } = d.bbox;
  const horizontal = width >= height;
  const w = round2(horizontal ? width : height);
  const out: Primitive[] = [{ ...base, type: "polygon", points: bboxPolygon(d.bbox), fill: "canvas-paper", stroke: null }];
  const mid = horizontal ? y + height / 2 : x + width / 2;
  const a = round2(horizontal ? x : y);
  const b = round2(a + w);
  const pt = (along: number, across: number): Pt => (horizontal ? [round2(along), round2(across)] : [round2(across), round2(along)]);

  if (d.swing === "SLIDING") {
    out.push({ ...base, type: "line", from: pt(a, mid), to: pt(b, mid), fill: null, stroke: "canvas-door", strokeWidth: 3 });
    return out;
  }
  const leaf = (hinge: number, free: number, r: number) => {
    const tip = pt(hinge, mid - r);
    const end = pt(free, mid);
    // Sweep flips with the hinge side and with the axis mirror between horizontal and vertical walls.
    const sweep = free > hinge === horizontal ? 1 : 0;
    out.push(
      { ...base, type: "line", from: pt(hinge, mid), to: tip, fill: null, stroke: "canvas-door", strokeWidth: 3 },
      { ...base, type: "path", d: `M ${tip[0]} ${tip[1]} A ${r} ${r} 0 0 ${sweep} ${end[0]} ${end[1]}`, fill: null, stroke: "canvas-door-swing", strokeWidth: 1.5 },
    );
  };
  if (d.swing === "DOUBLE") {
    const half = round2(w / 2);
    leaf(a, a + half, half);
    leaf(b, a + half, half);
  } else if (d.swing === "RIGHT") leaf(b, a, w);
  else leaf(a, b, w);
  return out;
}

function stairPrimitives(s: Stair): Primitive[] {
  const base = { elementId: s.id, kind: "stair", layer: "objects", fill: null } as const;
  const points = s.polygon?.length ? s.polygon.map((p) => [round2(p.x), round2(p.y)] as Pt) : bboxPolygon(s.bbox);
  const out: Primitive[] = [{ ...base, type: "polygon", points, stroke: "canvas-stair", strokeWidth: 2 }];
  const { x, y, width, height } = s.bbox;
  const along = width >= height;
  const long = along ? width : height;
  const short = along ? height : width;
  const treads = Math.min(24, Math.max(3, Math.round(long / Math.max(short / 6, 1))));
  for (let i = 1; i < treads; i++) {
    const at = round2((along ? x : y) + (long * i) / treads);
    out.push({
      ...base,
      type: "line",
      from: along ? [at, round2(y)] : [round2(x), at],
      to: along ? [at, round2(y + height)] : [round2(x + width), at],
      stroke: "canvas-stair",
      strokeWidth: 1,
    });
  }
  return out;
}

/** Flat, ordered, deterministic primitives in model coordinates. Colours are token names only. */
export function buildScene(model: FloorPlanModel | null | undefined, options: BuildSceneOptions = {}): Scene {
  if (!model) return { primitives: [], bounds: null, width: 0, height: 0, skipped: 0 };
  const { image_width: width, image_height: height, mm_per_pixel: mpp } = model.coordinate_system;
  const labelSize = round2(Math.max(width, height) / 70);
  const small = round2(labelSize * 0.72);
  let skipped = 0;
  const keep = <T>(list: T[], valid: (e: T) => boolean) =>
    list.filter((e) => {
      const ok = valid(e);
      if (!ok) skipped++;
      return ok;
    });
  const usable = <T extends { bbox: BBox }>(list: T[]) => keep(list, (e) => validBBox(e.bbox));

  const rooms = keep(model.rooms, validRoom);
  const walls = keep(model.walls, validWall);
  const windows = usable(model.windows);
  const doors = usable(model.doors);
  const columns = usable(model.columns);
  const stairs = usable(model.stairs);
  const furniture = usable(model.furniture);
  const dimensions = keep(model.dimensions, (d) => !!d.position && Number.isFinite(d.position.x) && Number.isFinite(d.position.y));

  const out: Primitive[] = [];

  for (const r of rooms)
    out.push({
      type: "polygon",
      elementId: r.id,
      kind: "room",
      layer: "rooms",
      points: r.polygon.map((p) => [round2(p.x), round2(p.y)]),
      fill: roomFillToken(r.room_type),
      stroke: "canvas-room-stroke",
      strokeWidth: 1,
    });

  for (const r of rooms) {
    const c = polygonCentroid(r.polygon);
    const base = { type: "text", elementId: r.id, kind: "room", layer: "labels", stroke: null } as const;
    out.push(
      { ...base, at: [round2(c.x), round2(c.y - labelSize * 0.25)], text: roomName(r), size: labelSize, weight: 500, fill: "canvas-room-label" },
      {
        ...base,
        at: [round2(c.x), round2(c.y + labelSize)],
        text: formatArea(r.area_px ?? polygonArea(r.polygon), mpp),
        size: small,
        mono: true,
        fill: "canvas-room-area",
      },
    );
  }

  const roomUse = new Map<string, number>();
  for (const r of rooms) for (const id of r.wall_ids) roomUse.set(id, (roomUse.get(id) ?? 0) + 1);
  for (const w of walls)
    out.push({
      type: "polygon",
      elementId: w.id,
      kind: "wall",
      layer: "walls",
      points: wallPolygon(w),
      fill: (roomUse.get(w.id) ?? 0) <= 1 ? "canvas-wall-exterior" : "canvas-wall",
      stroke: null,
    });

  for (const w of windows) {
    const base = { elementId: w.id, kind: "window", layer: "openings" } as const;
    const { x, y, width: bw, height: bh } = w.bbox;
    const glazing: [Pt, Pt] =
      bw >= bh
        ? [[round2(x), round2(y + bh / 2)], [round2(x + bw), round2(y + bh / 2)]]
        : [[round2(x + bw / 2), round2(y)], [round2(x + bw / 2), round2(y + bh)]];
    out.push(
      { ...base, type: "polygon", points: bboxPolygon(w.bbox), fill: "canvas-paper", stroke: "canvas-window", strokeWidth: 1.5 },
      { ...base, type: "line", from: glazing[0], to: glazing[1], fill: null, stroke: "canvas-window", strokeWidth: 1.5 },
    );
  }

  for (const d of doors) out.push(...doorPrimitives(d));
  for (const c of columns) out.push({ type: "polygon", elementId: c.id, kind: "column", layer: "objects", points: bboxPolygon(c.bbox), fill: "canvas-column", stroke: null });
  for (const s of stairs) out.push(...stairPrimitives(s));
  for (const f of furniture) out.push({ type: "polygon", elementId: f.id, kind: "furniture", layer: "objects", points: bboxPolygon(f.bbox), fill: null, stroke: "canvas-furniture", strokeWidth: 1.5 });

  const wallBounds = boundsOf(walls.flatMap((w) => [[w.start.x, w.start.y] as Pt, [w.end.x, w.end.y] as Pt]));
  for (const d of dimensions) {
    const { x, y } = d.position!;
    const base = { elementId: d.id, kind: "dimension", layer: "dimensions", fill: null, strokeWidth: 1 } as const;
    out.push({ ...base, type: "text", at: [round2(x), round2(y)], text: d.text, size: small, mono: true, stroke: null, fill: "canvas-dimension" });
    if (!d.span_px) continue;
    // CONTRACT-GAP: Dimension has no orientation. Beside the wall extent = vertical run; otherwise horizontal.
    const vertical = !!wallBounds && (x < wallBounds.minX || x > wallBounds.maxX);
    const half = d.span_px / 2;
    const tick = small / 3;
    const c = vertical ? x + small * 1.7 : y + small * 0.5;
    const seg = (a: number, across: number, b: number, across2: number): [Pt, Pt] =>
      vertical
        ? [[round2(across), round2(a)], [round2(across2), round2(b)]]
        : [[round2(a), round2(across)], [round2(b), round2(across2)]];
    const mid = vertical ? y : x;
    for (const [from, to] of [
      seg(mid - half, c, mid + half, c),
      seg(mid - half, c - tick, mid - half, c + tick),
      seg(mid + half, c - tick, mid + half, c + tick),
    ])
      out.push({ ...base, type: "line", from, to, stroke: "canvas-dimension" });
  }

  const primitives = options.layers ? out.filter((p) => options.layers![p.layer] !== false) : out;
  const pts = primitives.flatMap((p): Pt[] => (p.type === "polygon" ? p.points : p.type === "line" ? [p.from, p.to] : p.type === "text" ? [p.at] : []));
  return { primitives, bounds: boundsOf(pts), width, height, skipped };
}
