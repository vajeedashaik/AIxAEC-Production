// Structured commands built by point-and-click. Same shapes as CONTRACTS.md §3: the server does all geometry.
import type { CommandInput, Direction, Distance, ResizeMode, RoomType, Wall } from "@/contracts";

import { isVerticalWall } from "../viewer/render/geometry";

export const moveWall = (target_id: string, direction: Direction, distance: Distance): CommandInput => ({ operation: "MOVE_WALL", target_id, direction, distance });
export const deleteWall = (target_id: string): CommandInput => ({ operation: "DELETE_WALL", target_id });
export const addDoor = (target_id: string, position: number, width: Distance | null): CommandInput => ({ operation: "ADD_DOOR", target_id, position, width });
export const addWindow = (target_id: string, position: number, width: Distance | null): CommandInput => ({ operation: "ADD_WINDOW", target_id, position, width });
export const deleteDoor = (target_id: string): CommandInput => ({ operation: "DELETE_DOOR", target_id });
export const deleteWindow = (target_id: string): CommandInput => ({ operation: "DELETE_WINDOW", target_id });
export const setScale = (target_id: string, length_mm: number): CommandInput => ({ operation: "SET_SCALE", target_id, length_mm });
export const renameRoom = (target_id: string, name: string, room_type: RoomType | null): CommandInput => ({ operation: "RENAME_ROOM", target_id, name, room_type });
export const resizeRoom = (target_id: string, direction: Direction, distance: Distance, mode: ResizeMode): CommandInput => ({ operation: "RESIZE_ROOM", target_id, direction, distance, mode });

/** A wall only moves across its length. */
export const perpendicularDirections = (w: Pick<Wall, "start" | "end">): Direction[] => (isVerticalWall(w) ? ["LEFT", "RIGHT"] : ["UP", "DOWN"]);

/** Swap whatever targeted the command for the picked id. */
export function withTarget(command: Record<string, unknown>, target_id: string): CommandInput {
  const rest: Record<string, unknown> = { ...command, target_id };
  delete rest.target_query;
  return rest as unknown as CommandInput;
}
