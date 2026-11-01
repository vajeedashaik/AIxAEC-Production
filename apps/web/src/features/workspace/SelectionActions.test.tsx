import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { FloorPlanModel } from "@/contracts";
import apartmentJson from "@/mocks/fixtures/apartment.model.json";

import { indexElements } from "../viewer/render/geometry";
import { installDomStubs } from "../viewer/test-env";
import { commandFromInstruction, perpendicularDirections, withTarget } from "./commands";
import { SelectionActions } from "./SelectionActions";

const m = apartmentJson as unknown as FloorPlanModel;
const index = indexElements(m);
const H_WALL = m.walls.find((w) => w.start.y === w.end.y)!;
const V_WALL = m.walls.find((w) => w.start.x === w.end.x)!;
const ROOM = m.rooms[1];

beforeEach(installDomStubs);

function setup(id: string, hasScale = true) {
  const onCommand = vi.fn();
  render(
    <TooltipProvider>
      <SelectionActions entry={index.get(id)!} hasScale={hasScale} scaleRequested={false} onScaleConsumed={() => {}} onCommand={onCommand} />
    </TooltipProvider>,
  );
  return { onCommand, user: userEvent.setup() };
}

describe("selection actions send exact command payloads", () => {
  it("MOVE_WALL offers only perpendicular directions", async () => {
    const { onCommand, user } = setup(H_WALL.id);
    await user.click(screen.getByRole("button", { name: "Move" }));
    expect(screen.queryByRole("radio", { name: "Left" })).toBeNull();
    await user.click(screen.getByRole("radio", { name: "Down" }));
    const input = screen.getByLabelText("Distance");
    await user.clear(input);
    await user.type(input, "250");
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(onCommand).toHaveBeenCalledWith({ operation: "MOVE_WALL", target_id: H_WALL.id, direction: "DOWN", distance: { value: 250, unit: "mm" } });
  });

  it("MOVE_WALL without a scale defaults to px and disables mm", async () => {
    const { onCommand, user } = setup(V_WALL.id, false);
    await user.click(screen.getByRole("button", { name: "Move" }));
    expect(screen.getByRole("radio", { name: "mm" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(onCommand).toHaveBeenCalledWith({ operation: "MOVE_WALL", target_id: V_WALL.id, direction: "LEFT", distance: { value: 30, unit: "px" } });
  });

  it("refuses a non-positive distance", async () => {
    const { onCommand, user } = setup(V_WALL.id);
    await user.click(screen.getByRole("button", { name: "Move" }));
    await user.clear(screen.getByLabelText("Distance"));
    await user.type(screen.getByLabelText("Distance"), "0");
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
    expect(onCommand).not.toHaveBeenCalled();
  });

  it("DELETE_WALL", async () => {
    const { onCommand, user } = setup(H_WALL.id);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(onCommand).toHaveBeenCalledWith({ operation: "DELETE_WALL", target_id: H_WALL.id });
  });

  it("ADD_DOOR with position and width", async () => {
    const { onCommand, user } = setup(H_WALL.id);
    await user.click(screen.getByRole("button", { name: "Add door" }));
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(onCommand).toHaveBeenCalledWith({ operation: "ADD_DOOR", target_id: H_WALL.id, position: 0.5, width: { value: 900, unit: "mm" } });
  });

  it("ADD_WINDOW moves along the wall with the slider", async () => {
    const { onCommand, user } = setup(H_WALL.id);
    await user.click(screen.getByRole("button", { name: "Add window" }));
    screen.getByRole("slider").focus();
    await user.keyboard("{ArrowRight}{ArrowRight}");
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(onCommand).toHaveBeenCalledWith({ operation: "ADD_WINDOW", target_id: H_WALL.id, position: 0.52, width: { value: 1200, unit: "mm" } });
  });

  it("SET_SCALE with the real length in mm", async () => {
    const { onCommand, user } = setup(H_WALL.id, false);
    await user.click(screen.getByRole("button", { name: "Set scale" }));
    await user.type(screen.getByLabelText("Real length of this wall (mm)"), "4800");
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(onCommand).toHaveBeenCalledWith({ operation: "SET_SCALE", target_id: H_WALL.id, length_mm: 4800 });
  });

  it("RENAME_ROOM keeps room_type null when unchanged", async () => {
    const { onCommand, user } = setup(ROOM.id);
    await user.click(screen.getByRole("button", { name: "Rename" }));
    const name = screen.getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Galley");
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(onCommand).toHaveBeenCalledWith({ operation: "RENAME_ROOM", target_id: ROOM.id, name: "Galley", room_type: null });
  });

  it("RESIZE_ROOM with side, mode and distance", async () => {
    const { onCommand, user } = setup(ROOM.id);
    await user.click(screen.getByRole("button", { name: "Resize side" }));
    await user.click(screen.getByRole("radio", { name: "Up" }));
    await user.click(screen.getByRole("radio", { name: "Contract" }));
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(onCommand).toHaveBeenCalledWith({ operation: "RESIZE_ROOM", target_id: ROOM.id, direction: "UP", distance: { value: 300, unit: "mm" }, mode: "CONTRACT" });
  });

  it.each([
    ["DELETE_DOOR", m.doors[0].id],
    ["DELETE_WINDOW", m.windows[0].id],
  ])("%s", async (operation, id) => {
    const { onCommand, user } = setup(id);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(onCommand).toHaveBeenCalledWith({ operation, target_id: id });
  });

  it("renders nothing for elements without actions", () => {
    const { container } = render(<SelectionActions entry={index.get(m.columns[0].id)!} hasScale scaleRequested={false} onScaleConsumed={() => {}} onCommand={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("command helpers", () => {
  it("perpendicular directions follow wall orientation", () => {
    expect(perpendicularDirections(H_WALL)).toEqual(["UP", "DOWN"]);
    expect(perpendicularDirections(V_WALL)).toEqual(["LEFT", "RIGHT"]);
  });

  it("withTarget replaces target_query with target_id", () => {
    expect(withTarget({ operation: "DELETE_DOOR", target_query: "the door" }, "d1")).toEqual({ operation: "DELETE_DOOR", target_id: "d1" });
  });

  it("rebuilds only explicit commands from words", () => {
    const wall = { id: "w1", kind: "wall" as const };
    expect(commandFromInstruction("move the kitchen wall 300 mm left", wall)).toEqual({ operation: "MOVE_WALL", target_id: "w1", direction: "LEFT", distance: { value: 300, unit: "mm" } });
    expect(commandFromInstruction("delete the door", { id: "d1", kind: "door" })).toEqual({ operation: "DELETE_DOOR", target_id: "d1" });
    expect(commandFromInstruction("move the kitchen wall a bit", wall)).toBeNull();
    expect(commandFromInstruction("move the wall 3 m left", wall)).toBeNull();
    expect(commandFromInstruction("delete the door", wall)).toBeNull();
  });
});
