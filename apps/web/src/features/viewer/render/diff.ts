import type { ChangeSet, FloorPlanModel } from "@/contracts";

import { boundsOf, elementOutline, indexElements, type ModelElement } from "./geometry";
import type { CanvasToken, ChangeClass, OverlayPrimitive, Pt } from "./types";

function ghost(entry: ModelElement, points: Pt[], change: ChangeClass, token: CanvasToken): OverlayPrimitive {
  const before = change === "modified-before";
  return {
    type: "polygon",
    elementId: entry.element.id,
    kind: entry.kind,
    layer: entry.kind === "room" ? "rooms" : "walls",
    points,
    fill: before ? null : token,
    opacity: before ? undefined : 0.22,
    stroke: token,
    strokeWidth: 1.5,
    dashed: before || change === "removed",
    change,
  };
}

/** Preview-ghost primitives for a ChangeSet: added solid, modified before dashed + after solid, removed dashed and struck. */
export function previewOverlay(
  changes: ChangeSet | null | undefined,
  before: FloorPlanModel | null | undefined,
  after: FloorPlanModel | null | undefined,
): OverlayPrimitive[] {
  if (!changes) return [];
  const was = indexElements(before);
  const now = indexElements(after);
  const out: OverlayPrimitive[] = [];

  for (const id of changes.added ?? []) {
    const e = now.get(id);
    const pts = elementOutline(e);
    if (e && pts) out.push(ghost(e, pts, "added", "canvas-preview-add"));
  }
  for (const id of changes.modified ?? []) {
    const a = was.get(id);
    const b = now.get(id);
    const ap = elementOutline(a);
    const bp = elementOutline(b);
    if (a && ap) out.push(ghost(a, ap, "modified-before", "canvas-preview-modify"));
    if (b && bp) out.push(ghost(b, bp, "modified-after", "canvas-preview-modify"));
  }
  for (const id of changes.removed ?? []) {
    const e = was.get(id);
    const pts = elementOutline(e);
    if (!e || !pts) continue;
    const b = boundsOf(pts)!;
    out.push(ghost(e, pts, "removed", "canvas-preview-remove"), {
      type: "line",
      elementId: id,
      kind: e.kind,
      layer: "walls",
      from: [b.minX, b.minY],
      to: [b.maxX, b.maxY],
      fill: null,
      stroke: "canvas-preview-remove",
      strokeWidth: 1.5,
      change: "removed",
    });
  }
  return out;
}
