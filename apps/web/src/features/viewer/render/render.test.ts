import { describe, expect, it } from "vitest";

import type { FloorPlanModel } from "@/contracts";
import apartmentJson from "@/mocks/fixtures/apartment.model.json";
import unscaledJson from "@/mocks/fixtures/apartment.unscaled.model.json";

import { describeElement, elementLabel } from "./describe";
import { previewOverlay } from "./diff";
import { boundsOf, indexElements, pointInPolygon, polygonArea, polygonCentroid, polygonPerimeter, round2, wallPolygon } from "./geometry";
import { buildScene } from "./scene";
import { sceneToSvgString } from "./svg";
import { formatArea, formatLength, formatM2, formatMm, formatPx, niceFloor, pxToMm, scaleBar } from "./units";
import { fitTransform, gridSpacing, MAX_ZOOM, MIN_ZOOM, modelToScreen, panBy, screenToModel, zoomAt } from "./view-transform";

const apartment = apartmentJson as unknown as FloorPlanModel;
const unscaled = unscaledJson as unknown as FloorPlanModel;
const clone = (): FloorPlanModel => structuredClone(apartment);
const square = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }] as FloorPlanModel["rooms"][number]["polygon"];

describe("buildScene", () => {
  it("returns an empty scene for a null model", () => {
    expect(buildScene(null)).toEqual({ primitives: [], bounds: null, width: 0, height: 0, skipped: 0 });
  });

  it("orders primitives rooms, labels, walls, windows, doors, columns, stairs, furniture, dimensions", () => {
    const m = clone();
    m.furniture = [{ id: "f1", confidence: null, source: "DETECTED", bbox: { x: 1, y: 1, width: 5, height: 5 }, category: "sofa" }];
    const scene = buildScene(m);
    const firstOf = (test: (p: (typeof scene.primitives)[number]) => boolean) => scene.primitives.findIndex(test);
    const order = [
      firstOf((p) => p.kind === "room" && p.type === "polygon"),
      firstOf((p) => p.kind === "room" && p.type === "text"),
      firstOf((p) => p.kind === "wall"),
      firstOf((p) => p.kind === "window"),
      firstOf((p) => p.kind === "door"),
      firstOf((p) => p.kind === "column"),
      firstOf((p) => p.kind === "stair"),
      firstOf((p) => p.kind === "furniture"),
      firstOf((p) => p.kind === "dimension"),
    ];
    expect(order.every((v) => v >= 0)).toBe(true);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it("rounds coordinates to 2 dp", () => {
    const m = clone();
    m.walls[0].start = { x: 100.123456, y: 100.987654 };
    const scene = buildScene(m);
    const nums = scene.primitives.flatMap((p) => (p.type === "polygon" ? p.points.flat() : []));
    expect(nums.every((n) => n === round2(n))).toBe(true);
  });

  it("skips and counts invalid elements instead of throwing", () => {
    const m = clone();
    m.walls[0].end = { ...m.walls[0].start };
    m.doors[0].bbox.width = 0;
    m.rooms[0].polygon = m.rooms[0].polygon.slice(0, 2) as unknown as typeof square;
    m.dimensions[0].position = null;
    const scene = buildScene(m);
    expect(scene.skipped).toBe(4);
    expect(scene.primitives.some((p) => p.elementId === m.walls[0].id)).toBe(false);
  });

  it("styles every primitive with token names, never raw colours", () => {
    for (const p of buildScene(apartment).primitives) {
      for (const t of [p.fill, p.stroke]) if (t) expect(t).toMatch(/^canvas-[a-z-]+$/);
    }
  });

  it("uses a token per room type", () => {
    const fills = buildScene(apartment).primitives.filter((p) => p.kind === "room" && p.type === "polygon").map((p) => p.fill);
    expect(fills).toContain("canvas-room-living-room");
    expect(fills).toContain("canvas-room-kitchen");
  });

  it("distinguishes exterior from interior walls by shared rooms", () => {
    const fills = new Set(buildScene(apartment).primitives.filter((p) => p.kind === "wall").map((p) => p.fill));
    expect(fills).toEqual(new Set(["canvas-wall", "canvas-wall-exterior"]));
  });

  it("labels areas in m² only when scaled, px² otherwise", () => {
    const areas = (m: FloorPlanModel) => buildScene(m).primitives.flatMap((p) => (p.type === "text" && p.mono && p.kind === "room" ? [p.text] : []));
    expect(areas(apartment)[0]).toMatch(/m²$/);
    expect(areas(unscaled)[0]).toMatch(/px²$/);
  });

  it("draws a door leaf and a swing arc, and no arc for sliding", () => {
    const m = clone();
    const prims = (id: string, mm: FloorPlanModel) => buildScene(mm).primitives.filter((p) => p.elementId === id);
    expect(prims(m.doors[0].id, m).some((p) => p.type === "path")).toBe(true);
    m.doors[0].swing = "SLIDING";
    expect(prims(m.doors[0].id, m).some((p) => p.type === "path")).toBe(false);
    m.doors[0].swing = "DOUBLE";
    expect(prims(m.doors[0].id, m).filter((p) => p.type === "path")).toHaveLength(2);
  });

  it("draws stair treads", () => {
    const lines = buildScene(apartment).primitives.filter((p) => p.kind === "stair" && p.type === "line");
    expect(lines.length).toBeGreaterThanOrEqual(2);
  });

  it("can exclude layers", () => {
    const scene = buildScene(apartment, { layers: { labels: false, dimensions: false } });
    expect(scene.primitives.some((p) => p.layer === "labels" || p.layer === "dimensions")).toBe(false);
    expect(scene.primitives.some((p) => p.layer === "walls")).toBe(true);
  });

  it("computes bounds covering walls", () => {
    const b = buildScene(apartment).bounds!;
    expect(b.minX).toBeLessThanOrEqual(90);
    expect(b.maxX).toBeGreaterThanOrEqual(1300);
  });
});

describe("sceneToSvgString", () => {
  it("is byte-identical across runs", () => {
    expect(sceneToSvgString(buildScene(apartment))).toBe(sceneToSvgString(buildScene(clone())));
  });

  it("matches the snapshot for a tiny model", () => {
    const m: FloorPlanModel = {
      ...clone(),
      doors: [],
      windows: [],
      columns: [],
      stairs: [],
      dimensions: [],
      walls: [{ id: "w1", confidence: null, source: "DETECTED", start: { x: 0, y: 5 }, end: { x: 10.126, y: 5 }, thickness_px: 2 }],
      rooms: [{ id: "r1", confidence: null, source: "DETECTED", polygon: square, wall_ids: ["w1"], label_text: "A & B", room_type: "KITCHEN", room_type_source: null, room_type_confidence: null, area_px: 100 }],
    };
    expect(sceneToSvgString(buildScene(m))).toMatchSnapshot();
  });

  it("escapes markup in labels", () => {
    const m = clone();
    m.rooms[0].label_text = `<script>alert("x")</script>`;
    const svg = sceneToSvgString(buildScene(m));
    expect(svg).not.toContain("<script>");
    expect(svg).toContain("&lt;script&gt;alert(&quot;x&quot;)");
  });
});

describe("view transform", () => {
  const samples = [
    { k: 1, x: 0, y: 0 },
    { k: 0.37, x: 120.5, y: -44 },
    { k: 17.3, x: -900, y: 321.25 },
    { k: 0.02, x: 3, y: 9 },
    { k: 40, x: -12345, y: 678 },
  ];
  const points = [{ x: 0, y: 0 }, { x: 412.25, y: 88.5 }, { x: 1600, y: 1200 }, { x: 3.33, y: 7.77 }];

  it.each(samples)("modelToScreen and screenToModel are inverses at k=$k", (t) => {
    for (const p of points) {
      const back = screenToModel(t, modelToScreen(t, p));
      expect(back.x).toBeCloseTo(p.x, 6);
      expect(back.y).toBeCloseTo(p.y, 6);
    }
  });

  it("keeps the cursor's model point fixed when zooming", () => {
    const t = { k: 0.8, x: 40, y: -20 };
    const cursor = { x: 333, y: 222 };
    const before = screenToModel(t, cursor);
    const after = screenToModel(zoomAt(t, cursor, 1.7), cursor);
    expect(after.x).toBeCloseTo(before.x, 6);
    expect(after.y).toBeCloseTo(before.y, 6);
  });

  it("clamps zoom to 0.02 and 40", () => {
    expect(zoomAt({ k: 1, x: 0, y: 0 }, { x: 0, y: 0 }, 1e6).k).toBe(MAX_ZOOM);
    expect(zoomAt({ k: 1, x: 0, y: 0 }, { x: 0, y: 0 }, 1e-6).k).toBe(MIN_ZOOM);
  });

  it("does not drift when zoom is already at the limit", () => {
    const t = { k: MAX_ZOOM, x: 11, y: 22 };
    expect(zoomAt(t, { x: 100, y: 100 }, 2)).toEqual(t);
  });

  it("pans by adding to the translation", () => {
    expect(panBy({ k: 2, x: 1, y: 1 }, 5, -3)).toEqual({ k: 2, x: 6, y: -2 });
  });

  it("fits bounds centred inside the padded viewport", () => {
    const t = fitTransform({ minX: 100, minY: 100, maxX: 1100, maxY: 600 }, { width: 1200, height: 800 }, 100);
    expect(t.k).toBe(1);
    expect(modelToScreen(t, { x: 600, y: 350 })).toEqual({ x: 600, y: 400 });
  });

  it("falls back to identity without bounds or viewport", () => {
    expect(fitTransform(null, { width: 100, height: 100 })).toEqual({ k: 1, x: 0, y: 0 });
    expect(fitTransform({ minX: 0, minY: 0, maxX: 1, maxY: 1 }, { width: 0, height: 0 })).toEqual({ k: 1, x: 0, y: 0 });
  });

  it.each([0.02, 0.1, 0.5, 1, 3, 17, 40])("keeps the grid readable at zoom %s", (k) => {
    const { minor, major } = gridSpacing(k);
    expect(minor).toBeGreaterThanOrEqual(14 - 1e-6);
    expect(minor).toBeLessThan(14 * 2.6);
    expect(major).toBeCloseTo(minor * 5);
  });
});

describe("geometry", () => {
  it("computes area, perimeter and centroid", () => {
    expect(polygonArea(square)).toBe(100);
    expect(polygonPerimeter(square)).toBe(40);
    expect(polygonCentroid(square)).toEqual({ x: 5, y: 5 });
  });

  it("falls back to the vertex mean for a degenerate polygon", () => {
    expect(polygonCentroid([{ x: 0, y: 0 }, { x: 2, y: 0 }, { x: 4, y: 0 }])).toEqual({ x: 2, y: 0 });
  });

  it("tests point in polygon", () => {
    expect(pointInPolygon({ x: 5, y: 5 }, square)).toBe(true);
    expect(pointInPolygon({ x: 15, y: 5 }, square)).toBe(false);
  });

  it("builds a wall polygon from centre-line and thickness", () => {
    expect(wallPolygon({ start: { x: 0, y: 0 }, end: { x: 10, y: 0 }, thickness_px: 4 })).toEqual([[-2, 2], [12, 2], [12, -2], [-2, -2]]);
  });

  it("returns null bounds for nothing", () => {
    expect(boundsOf([])).toBeNull();
  });
});

describe("units never fake a conversion", () => {
  it.each([null, undefined, 0, -1, NaN])("returns no metric value for mm_per_pixel=%s", (mpp) => {
    expect(pxToMm(100, mpp)).toBeNull();
    expect(formatMm(100, mpp)).toBeNull();
    expect(formatM2(100, mpp)).toBeNull();
    expect(formatLength(100, mpp)).toBe("100 px");
    expect(formatArea(100, mpp)).toBe("100 px²");
  });

  it("converts with mm_per_pixel", () => {
    expect(formatMm(360, 10)).toBe("3600 mm");
    expect(formatM2(1_000_000, 10)).toBe("100 m²");
    expect(formatPx(1.239)).toBe("1.24 px");
  });

  it("labels the scale bar in px without a scale and in metric with one", () => {
    expect(scaleBar(1, null).label).toBe("50 px");
    expect(scaleBar(1, 10).label).toBe("500 mm");
    expect(scaleBar(0.1, 10).label).toBe("5 m");
    expect(scaleBar(1, 10).widthPx).toBe(50);
  });

  it("floors to 1/2/5 steps", () => {
    expect([niceFloor(7), niceFloor(19), niceFloor(0.3), niceFloor(0)]).toEqual([5, 10, 0.2, 0]);
  });
});

describe("previewOverlay", () => {
  const moved = () => {
    const after = clone();
    after.walls[0].start.x += 30;
    after.walls[0].end.x += 30;
    return after;
  };

  it("draws modified as before dashed and after solid", () => {
    const id = apartment.walls[0].id;
    const out = previewOverlay({ added: [], modified: [id], removed: [] }, apartment, moved());
    expect(out.map((p) => [p.change, !!p.dashed, p.stroke])).toEqual([
      ["modified-before", true, "canvas-preview-modify"],
      ["modified-after", false, "canvas-preview-modify"],
    ]);
  });

  it("draws added in the add token from the after model", () => {
    const after = clone();
    const door = { ...after.doors[0], id: "new-door" };
    after.doors.push(door);
    const out = previewOverlay({ added: ["new-door"], modified: [], removed: [] }, apartment, after);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ change: "added", stroke: "canvas-preview-add", kind: "door" });
  });

  it("draws removed dashed and struck in the remove token from the before model", () => {
    const id = apartment.doors[0].id;
    const after = clone();
    after.doors = after.doors.slice(1);
    const out = previewOverlay({ added: [], modified: [], removed: [id] }, apartment, after);
    expect(out.map((p) => p.type)).toEqual(["polygon", "line"]);
    expect(out.every((p) => p.change === "removed" && p.stroke === "canvas-preview-remove")).toBe(true);
    expect(out[0].dashed).toBe(true);
  });

  it("ignores unknown ids and null change sets", () => {
    expect(previewOverlay({ added: ["x"], modified: ["y"], removed: ["z"] }, apartment, apartment)).toEqual([]);
    expect(previewOverlay(null, apartment, apartment)).toEqual([]);
  });
});

describe("describeElement", () => {
  it("gives walls px length with mm when scaled and links rooms", () => {
    const d = describeElement(apartment, apartment.walls[0].id)!;
    expect(d.facts[0]).toEqual({ label: "Length", value: "500 px", metric: "5000 mm" });
    expect(d.links.some((l) => l.kind === "room")).toBe(true);
  });

  it("never gives metric facts when unscaled", () => {
    const d = describeElement(unscaled, unscaled.rooms[0].id)!;
    expect(d.facts.every((f) => f.metric === null)).toBe(true);
    expect(d.roomType?.type).toBe("LIVING_ROOM");
  });

  it("links an opening to its wall", () => {
    const d = describeElement(apartment, apartment.doors[0].id)!;
    expect(d.links).toHaveLength(1);
    expect(d.links[0].kind).toBe("wall");
  });

  it("returns null for an unknown id", () => {
    expect(describeElement(apartment, "nope")).toBeNull();
  });

  it("labels elements for lists", () => {
    const idx = indexElements(apartment);
    expect(elementLabel(idx.get(apartment.rooms[0].id)!)).toBe("LIVING");
    expect(elementLabel(idx.get(apartment.walls[0].id)!)).toBe("Horizontal wall, 500 px");
  });
});
