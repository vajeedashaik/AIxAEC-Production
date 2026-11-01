import type { FloorPlanModel } from "@/contracts";

/** Deterministic grid plan with about `target` elements, for pan/zoom performance runs. */
export function syntheticModel(target = 500): FloorPlanModel {
  // Each cell yields one room, 2 own walls and 2 openings; the closing edge walls are extra.
  const cells = Math.ceil(Math.sqrt(target / 5));
  const size = 200;
  const margin = 50;
  const id = (kind: number, n: number) => `00000000-0000-4000-8000-${String(kind).padStart(4, "0")}${String(n).padStart(8, "0")}`;
  const base = { confidence: 0.9, source: "DETECTED" as const };
  const m: FloorPlanModel = {
    schema_version: 1,
    id: id(0, 0),
    floorplan_id: id(0, 1),
    coordinate_system: { image_width: cells * size + margin * 2, image_height: cells * size + margin * 2, mm_per_pixel: 10, calibration_source: "MANUAL", calibration_confidence: 1 },
    walls: [],
    doors: [],
    windows: [],
    columns: [],
    stairs: [],
    furniture: [],
    dimensions: [],
    rooms: [],
  };
  let n = 0;
  const wall = (x1: number, y1: number, x2: number, y2: number) => {
    const wallId = id(1, n++);
    m.walls.push({ ...base, id: wallId, start: { x: x1, y: y1 }, end: { x: x2, y: y2 }, thickness_px: 10 });
    return wallId;
  };
  const types = ["BEDROOM", "KITCHEN", "BATHROOM", "LIVING_ROOM", "OFFICE", "HALLWAY"] as const;
  for (let r = 0; r < cells; r++)
    for (let c = 0; c < cells; c++) {
      const x = margin + c * size;
      const y = margin + r * size;
      const top = wall(x, y, x + size, y);
      const left = wall(x, y, x, y + size);
      const roomId = id(2, r * cells + c);
      m.rooms.push({
        ...base,
        id: roomId,
        polygon: [{ x, y }, { x: x + size, y }, { x: x + size, y: y + size }, { x, y: y + size }],
        wall_ids: [top, left],
        label_text: `R${r}-${c}`,
        room_type: types[(r + c) % types.length],
        room_type_source: "INFERRED",
        room_type_confidence: 0.8,
        area_px: size * size,
      });
      m.doors.push({ ...base, id: id(3, r * cells + c), bbox: { x: x + 60, y: y - 5, width: 60, height: 10 }, wall_id: top, width_px: 60, swing: "LEFT" });
      m.windows.push({ ...base, id: id(4, r * cells + c), bbox: { x: x - 5, y: y + 60, width: 10, height: 80 }, wall_id: left, width_px: 80 });
    }
  for (let i = 0; i < cells; i++) {
    wall(margin + cells * size, margin + i * size, margin + cells * size, margin + (i + 1) * size);
    wall(margin + i * size, margin + cells * size, margin + (i + 1) * size, margin + cells * size);
  }
  return m;
}
