import type { Point } from "@/contracts";

import type { Bounds } from "./types";
import { niceFloor } from "./units";

/** screen = model × k + (x, y) */
export interface ViewTransform {
  k: number;
  x: number;
  y: number;
}
export interface Size {
  width: number;
  height: number;
}

export const MIN_ZOOM = 0.02;
export const MAX_ZOOM = 40;
export const IDENTITY: ViewTransform = { k: 1, x: 0, y: 0 };

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export const modelToScreen = (t: ViewTransform, p: Point): Point => ({ x: p.x * t.k + t.x, y: p.y * t.k + t.y });
export const screenToModel = (t: ViewTransform, p: Point): Point => ({ x: (p.x - t.x) / t.k, y: (p.y - t.y) / t.k });
export const transformAttr = (t: ViewTransform) => `translate(${t.x} ${t.y}) scale(${t.k})`;

export function fitTransform(bounds: Bounds | null, viewport: Size, padding = 48): ViewTransform {
  if (!bounds || viewport.width <= 0 || viewport.height <= 0) return IDENTITY;
  const w = Math.max(bounds.maxX - bounds.minX, 1);
  const h = Math.max(bounds.maxY - bounds.minY, 1);
  const k = clamp(
    Math.min(Math.max(viewport.width - padding * 2, 1) / w, Math.max(viewport.height - padding * 2, 1) / h),
    MIN_ZOOM,
    MAX_ZOOM,
  );
  return { k, x: (viewport.width - w * k) / 2 - bounds.minX * k, y: (viewport.height - h * k) / 2 - bounds.minY * k };
}

/** Zoom keeping the model point under `point` (screen coordinates) fixed. */
export function zoomAt(t: ViewTransform, point: Point, factor: number): ViewTransform {
  const k = clamp(t.k * factor, MIN_ZOOM, MAX_ZOOM);
  if (k === t.k) return t;
  const m = screenToModel(t, point);
  return { k, x: point.x - m.x * k, y: point.y - m.y * k };
}

export const panBy = (t: ViewTransform, dx: number, dy: number): ViewTransform => ({ k: t.k, x: t.x + dx, y: t.y + dy });

/** Transform at zoom `k` centring the model point `m` in the viewport. */
export const centerOn = (m: Point, viewport: Size, k: number): ViewTransform => ({
  k,
  x: viewport.width / 2 - m.x * k,
  y: viewport.height / 2 - m.y * k,
});

/** Grid spacing in screen px: a 1/2/5 × 10^n model step that never gets denser than `minScreenPx`. */
export function gridSpacing(k: number, minScreenPx = 14): { minor: number; major: number } {
  const target = minScreenPx / k;
  const floor = niceFloor(target);
  // Next step up the 1/2/5 ladder from the floor.
  const step = floor >= target ? floor : niceFloor(floor * 2.5 + floor * 1e-6) >= target ? niceFloor(floor * 2.5 + floor * 1e-6) : floor * 5;
  return { minor: step * k, major: step * k * 5 };
}
