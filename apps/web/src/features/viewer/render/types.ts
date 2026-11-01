import type { ElementKind } from "@/contracts";

export type Pt = readonly [x: number, y: number];
export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/** A design token name, without var(); never a raw colour. */
export type CanvasToken = `canvas-${string}`;
export const tokenVar = (t: CanvasToken | null) => (t ? `var(--${t})` : "none");

export const LAYERS = ["rooms", "labels", "walls", "openings", "objects", "dimensions"] as const;
export type LayerId = (typeof LAYERS)[number];

interface PrimitiveBase {
  elementId: string;
  kind: ElementKind;
  layer: LayerId;
  fill: CanvasToken | null;
  stroke: CanvasToken | null;
  strokeWidth?: number;
  dashed?: boolean;
  opacity?: number;
}
export interface PolygonPrimitive extends PrimitiveBase {
  type: "polygon";
  points: Pt[];
}
export interface LinePrimitive extends PrimitiveBase {
  type: "line";
  from: Pt;
  to: Pt;
}
export interface PathPrimitive extends PrimitiveBase {
  type: "path";
  d: string;
}
export interface TextPrimitive extends PrimitiveBase {
  type: "text";
  at: Pt;
  text: string;
  size: number;
  mono?: boolean;
  weight?: number;
}
export type Primitive = PolygonPrimitive | LinePrimitive | PathPrimitive | TextPrimitive;

export interface Scene {
  primitives: Primitive[];
  bounds: Bounds | null;
  width: number;
  height: number;
  /** Elements dropped because their geometry was invalid. */
  skipped: number;
}

export type ChangeClass = "added" | "modified-before" | "modified-after" | "removed";
export type OverlayPrimitive = (PolygonPrimitive | LinePrimitive) & { change: ChangeClass };
