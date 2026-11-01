// Structured commands built by point-and-click. Same shapes as CONTRACTS.md §3: the server does all geometry.
import type { Candidate, CommandInput, Direction, Distance, ElementKind, ResizeMode, RoomType, Wall } from "@/contracts";

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

const DIRECTIONS: Record<string, Direction> = { left: "LEFT", west: "LEFT", right: "RIGHT", east: "RIGHT", up: "UP", north: "UP", down: "DOWN", south: "DOWN" };

function explicitDistance(t: string): Distance | null {
  const m = t.match(/(\d+(?:\.\d+)?)\s*(mm|millimet(?:er|re)s?|px|pixels?)\b/);
  if (!m || !(Number(m[1]) > 0)) return null;
  return { value: Number(m[1]), unit: m[2].startsWith("p") ? "px" : "mm" };
}

/**
 * CONTRACT-GAP: a CLARIFICATION on a typed instruction arrives with `command: null`, so there is nothing to re-send
 * with target_id. Until the API returns the parsed command (see HANDOFF), rebuild only commands the words state
 * outright for the picked kind. Anything else returns null and the user is asked to rephrase: never guess.
 */
export function commandFromInstruction(instruction: string, candidate: Pick<Candidate, "id"> & { kind: ElementKind }): CommandInput | null {
  const t = instruction.toLowerCase();
  const id = candidate.id;
  const deletes = /\b(delete|remove)\b/.test(t);
  if (candidate.kind === "door" && deletes && /\bdoor\b/.test(t)) return deleteDoor(id);
  if (candidate.kind === "window" && deletes && /\bwindow\b/.test(t)) return deleteWindow(id);
  if (candidate.kind !== "wall") return null;
  if (deletes && /\bwall\b/.test(t)) return deleteWall(id);
  if (/\b(move|shift|push|nudge)\b/.test(t)) {
    const distance = explicitDistance(t);
    const word = Object.keys(DIRECTIONS).find((d) => new RegExp(`\\b${d}\\b`).test(t));
    return distance && word ? moveWall(id, DIRECTIONS[word], distance) : null;
  }
  return null;
}
