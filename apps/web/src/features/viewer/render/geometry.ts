import type { BBox, Column, Dimension, Door, FloorPlanModel, Furniture, Point, Room, Stair, Wall, Window } from "@/contracts";

import type { Bounds, Pt } from "./types";

export const DEFAULT_WALL_THICKNESS_PX = 8;

/** 2-dp rounding, normalising -0 so output stays byte-identical. */
export const round2 = (n: number) => {
  const v = Math.round(n * 100) / 100;
  return v === 0 ? 0 : v;
};

const finite = (...ns: number[]) => ns.every(Number.isFinite);

export function polygonArea(points: readonly Point[]): number {
  let s = 0;
  points.forEach((a, i) => {
    const b = points[(i + 1) % points.length];
    s += a.x * b.y - b.x * a.y;
  });
  return Math.abs(s) / 2;
}

export function polygonPerimeter(points: readonly Point[]): number {
  return points.reduce((sum, a, i) => {
    const b = points[(i + 1) % points.length];
    return sum + Math.hypot(b.x - a.x, b.y - a.y);
  }, 0);
}

/** Area-weighted centroid; falls back to the vertex mean for degenerate polygons. */
export function polygonCentroid(points: readonly Point[]): Point {
  let a2 = 0;
  let cx = 0;
  let cy = 0;
  points.forEach((p, i) => {
    const q = points[(i + 1) % points.length];
    const cross = p.x * q.y - q.x * p.y;
    a2 += cross;
    cx += (p.x + q.x) * cross;
    cy += (p.y + q.y) * cross;
  });
  if (Math.abs(a2) < 1e-9) {
    const n = points.length || 1;
    return { x: points.reduce((s, p) => s + p.x, 0) / n, y: points.reduce((s, p) => s + p.y, 0) / n };
  }
  return { x: cx / (3 * a2), y: cy / (3 * a2) };
}

export function pointInPolygon(p: Point, polygon: readonly Point[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[i];
    const b = polygon[j];
    if (a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

export function boundsOf(points: readonly Pt[]): Bounds | null {
  if (!points.length) return null;
  let [minX, minY] = points[0];
  let [maxX, maxY] = points[0];
  for (const [x, y] of points) {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  return { minX, minY, maxX, maxY };
}

export const wallLength = (w: Pick<Wall, "start" | "end">) => Math.hypot(w.end.x - w.start.x, w.end.y - w.start.y);
export const isVerticalWall = (w: Pick<Wall, "start" | "end">) => Math.abs(w.end.x - w.start.x) < Math.abs(w.end.y - w.start.y);

/** Distance from p to the wall's centre-line segment. */
export function distanceToWall(p: Point, w: Pick<Wall, "start" | "end">): number {
  const dx = w.end.x - w.start.x, dy = w.end.y - w.start.y;
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((p.x - w.start.x) * dx + (p.y - w.start.y) * dy) / len2)) : 0;
  return Math.hypot(p.x - (w.start.x + t * dx), p.y - (w.start.y + t * dy));
}

/** The wall's footprint from centre-line + thickness, with square caps so corners close. */
export function wallPolygon(w: Pick<Wall, "start" | "end" | "thickness_px">): Pt[] {
  const t = (w.thickness_px ?? DEFAULT_WALL_THICKNESS_PX) / 2;
  const len = wallLength(w);
  const ux = (w.end.x - w.start.x) / len;
  const uy = (w.end.y - w.start.y) / len;
  const [ax, ay, bx, by] = [w.start.x - ux * t, w.start.y - uy * t, w.end.x + ux * t, w.end.y + uy * t];
  const [nx, ny] = [-uy * t, ux * t];
  return [
    [round2(ax + nx), round2(ay + ny)],
    [round2(bx + nx), round2(by + ny)],
    [round2(bx - nx), round2(by - ny)],
    [round2(ax - nx), round2(ay - ny)],
  ];
}

export const bboxPolygon = (b: BBox): Pt[] => [
  [round2(b.x), round2(b.y)],
  [round2(b.x + b.width), round2(b.y)],
  [round2(b.x + b.width), round2(b.y + b.height)],
  [round2(b.x), round2(b.y + b.height)],
];

export const validBBox = (b: BBox | undefined | null) => !!b && finite(b.x, b.y, b.width, b.height) && b.width > 0 && b.height > 0;
export const validWall = (w: Wall) => !!w.start && !!w.end && finite(w.start.x, w.start.y, w.end.x, w.end.y) && wallLength(w) > 0;
export const validRoom = (r: Room) => Array.isArray(r.polygon) && r.polygon.length >= 3 && r.polygon.every((p) => finite(p.x, p.y));

export type ModelElement =
  | { kind: "room"; element: Room }
  | { kind: "wall"; element: Wall }
  | { kind: "door"; element: Door }
  | { kind: "window"; element: Window }
  | { kind: "column"; element: Column }
  | { kind: "stair"; element: Stair }
  | { kind: "furniture"; element: Furniture }
  | { kind: "dimension"; element: Dimension };

export function indexElements(model: FloorPlanModel | null | undefined): Map<string, ModelElement> {
  const map = new Map<string, ModelElement>();
  if (!model) return map;
  for (const element of model.rooms) map.set(element.id, { kind: "room", element });
  for (const element of model.walls) map.set(element.id, { kind: "wall", element });
  for (const element of model.doors) map.set(element.id, { kind: "door", element });
  for (const element of model.windows) map.set(element.id, { kind: "window", element });
  for (const element of model.columns) map.set(element.id, { kind: "column", element });
  for (const element of model.stairs) map.set(element.id, { kind: "stair", element });
  for (const element of model.furniture) map.set(element.id, { kind: "furniture", element });
  for (const element of model.dimensions) map.set(element.id, { kind: "dimension", element });
  return map;
}

/** Footprint used for highlights, ghosts and zoom-to-element. Null when the element has no valid geometry. */
export function elementOutline(entry: ModelElement | undefined): Pt[] | null {
  if (!entry) return null;
  switch (entry.kind) {
    case "room":
      return validRoom(entry.element) ? entry.element.polygon.map((p) => [round2(p.x), round2(p.y)] as Pt) : null;
    case "wall":
      return validWall(entry.element) ? wallPolygon(entry.element) : null;
    case "dimension": {
      const p = entry.element.position;
      if (!p || !finite(p.x, p.y)) return null;
      const half = (entry.element.text.length * 16) / 2 || 1;
      return bboxPolygon({ x: p.x - half, y: p.y - 16, width: half * 2, height: 24 });
    }
    default:
      return validBBox(entry.element.bbox) ? bboxPolygon(entry.element.bbox) : null;
  }
}
