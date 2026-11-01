// The landing demo's plan, in millimetres. A real (tiny) calculation, so every number on the page adds up.
export const PLAN_W = 9000;
export const PLAN_H = 6400;
export const SPLIT_Y = 3600; // the wall between the top and bottom rows
const HALL_X = [3400, 4800]; // fixed walls of the bottom row
const MIN_ROOM_MM = 1200;

export type MovableWall = "kitchen" | "bath";
export type PlanState = Record<MovableWall, number>; // x of each movable wall

export const INITIAL_PLAN: PlanState = { kitchen: 5400, bath: 6400 };

export interface PlanRoom {
  id: string;
  label: string;
  fill: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export function planRooms({ kitchen, bath }: PlanState): PlanRoom[] {
  const top = { y: 0, h: SPLIT_Y };
  const bottom = { y: SPLIT_Y, h: PLAN_H - SPLIT_Y };
  return [
    { id: "living", label: "Living room", fill: "living-room", x: 0, w: kitchen, ...top },
    { id: "kitchen", label: "Kitchen", fill: "kitchen", x: kitchen, w: PLAN_W - kitchen, ...top },
    { id: "bed1", label: "Bedroom", fill: "bedroom", x: 0, w: HALL_X[0], ...bottom },
    { id: "hall", label: "Hall", fill: "hallway", x: HALL_X[0], w: HALL_X[1] - HALL_X[0], ...bottom },
    { id: "bath", label: "Bath", fill: "bathroom", x: HALL_X[1], w: bath - HALL_X[1], ...bottom },
    { id: "bed2", label: "Bedroom 2", fill: "bedroom", x: bath, w: PLAN_W - bath, ...bottom },
  ];
}

/** "19.44 m²". Always 2 dp: rounding a measurement further would be a silent loss. */
export const areaLabel = (room: Pick<PlanRoom, "w" | "h">) => `${((room.w * room.h) / 1e6).toFixed(2)} m²`;

export type MoveResult = { ok: true; plan: PlanState; summary: string } | { ok: false; detail: string };

const WALL_LIMITS: Record<MovableWall, [number, number]> = {
  kitchen: [0, PLAN_W],
  bath: [HALL_X[1], PLAN_W],
};
const WALL_ROOMS: Record<MovableWall, [string, string]> = { kitchen: ["Living room", "Kitchen"], bath: ["Bath", "Bedroom 2"] };

/** Moves a wall left by `mm`, or rejects with the constraint it would break. Same outcome types as the real API. */
export function moveWallLeft(plan: PlanState, wall: MovableWall, mm: number): MoveResult {
  const [low, high] = WALL_LIMITS[wall];
  const x = plan[wall] - mm;
  const [left, right] = WALL_ROOMS[wall];
  if (x - low < MIN_ROOM_MM) return { ok: false, detail: `${left} would be narrower than ${MIN_ROOM_MM} mm.` };
  if (high - x < MIN_ROOM_MM) return { ok: false, detail: `${right} would be narrower than ${MIN_ROOM_MM} mm.` };
  return { ok: true, plan: { ...plan, [wall]: x }, summary: `Moved wall ${mm} mm left. ${left} and ${right.toLowerCase()} resized.` };
}
