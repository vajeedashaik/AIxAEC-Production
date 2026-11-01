import type { ElementKind, FloorPlanModel, Source } from "@/contracts";

import { indexElements, isVerticalWall, polygonArea, polygonPerimeter, wallLength, type ModelElement } from "./geometry";
import { roomName } from "./scene";
import { formatM2, formatMm, formatPx, formatPx2 } from "./units";

export interface Fact {
  label: string;
  value: string;
  metric: string | null;
}
export interface ElementLink {
  id: string;
  kind: ElementKind;
  label: string;
}
export interface ElementDescription {
  id: string;
  kind: ElementKind;
  title: string;
  facts: Fact[];
  source: Source;
  confidence: number | null;
  roomType?: { type: string; source: Source | null; confidence: number | null };
  links: ElementLink[];
}

const KIND_TITLE: Record<ElementKind, string> = {
  wall: "Wall",
  room: "Room",
  door: "Door",
  window: "Window",
  column: "Column",
  stair: "Stair",
  furniture: "Furniture",
  dimension: "Dimension",
};

/** Short human label for lists, links and chips. */
export function elementLabel(entry: ModelElement): string {
  switch (entry.kind) {
    case "room":
      return roomName(entry.element);
    case "wall":
      return `${isVerticalWall(entry.element) ? "Vertical" : "Horizontal"} wall, ${formatPx(wallLength(entry.element))}`;
    case "door":
    case "window":
      return `${KIND_TITLE[entry.kind]} at (${Math.round(entry.element.bbox.x)}, ${Math.round(entry.element.bbox.y)})`;
    case "dimension":
      return `Dimension ${entry.element.text}`;
    case "furniture":
      return entry.element.category || "Furniture";
    default:
      return KIND_TITLE[entry.kind];
  }
}

/** The sidebar facts for one element. Metric values are null without a calibrated scale. */
export function describeElement(model: FloorPlanModel, id: string): ElementDescription | null {
  const index = indexElements(model);
  const entry = index.get(id);
  if (!entry) return null;
  const mpp = model.coordinate_system.mm_per_pixel;
  const len = (label: string, px: number): Fact => ({ label, value: formatPx(px), metric: formatMm(px, mpp) });
  const link = (e: ModelElement): ElementLink => ({ id: e.element.id, kind: e.kind, label: elementLabel(e) });
  const out: ElementDescription = {
    id,
    kind: entry.kind,
    title: entry.kind === "room" ? roomName(entry.element) : KIND_TITLE[entry.kind],
    facts: [],
    source: entry.element.source,
    confidence: entry.element.confidence,
    links: [],
  };
  const openings = (wallIds: Set<string>) => [
    ...model.doors.filter((d) => d.wall_id && wallIds.has(d.wall_id)).map((element) => link({ kind: "door", element })),
    ...model.windows.filter((d) => d.wall_id && wallIds.has(d.wall_id)).map((element) => link({ kind: "window", element })),
  ];

  switch (entry.kind) {
    case "wall": {
      const w = entry.element;
      out.facts.push(len("Length", wallLength(w)));
      if (w.thickness_px) out.facts.push(len("Thickness", w.thickness_px));
      out.links.push(...model.rooms.filter((r) => r.wall_ids.includes(id)).map((element) => link({ kind: "room", element })), ...openings(new Set([id])));
      break;
    }
    case "room": {
      const r = entry.element;
      const area = r.area_px ?? polygonArea(r.polygon);
      out.facts.push({ label: "Area", value: formatPx2(area), metric: formatM2(area, mpp) }, len("Perimeter", polygonPerimeter(r.polygon)));
      out.roomType = { type: r.room_type, source: r.room_type_source, confidence: r.room_type_confidence };
      for (const w of r.wall_ids) {
        const e = index.get(w);
        if (e) out.links.push(link(e));
      }
      out.links.push(...openings(new Set(r.wall_ids)));
      break;
    }
    case "door":
    case "window": {
      const o = entry.element;
      out.facts.push(len("Width", o.width_px ?? Math.max(o.bbox.width, o.bbox.height)));
      if (entry.kind === "door" && entry.element.swing) out.facts.push({ label: "Swing", value: entry.element.swing.toLowerCase(), metric: null });
      const wall = o.wall_id ? index.get(o.wall_id) : undefined;
      if (wall) out.links.push(link(wall));
      break;
    }
    case "dimension": {
      const d = entry.element;
      out.facts.push({ label: "Text", value: d.text, metric: d.value_mm ? `${d.value_mm} mm` : null });
      if (d.span_px) out.facts.push(len("Span", d.span_px));
      break;
    }
    default: {
      const b = entry.element.bbox;
      out.facts.push(len("Width", b.width), len("Depth", b.height));
    }
  }
  return out;
}
