import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { FloorPlanModel } from "@/contracts";
import apartmentJson from "@/mocks/fixtures/apartment.model.json";
import unscaledJson from "@/mocks/fixtures/apartment.unscaled.model.json";

import { previewOverlay } from "../render/diff";
import { installDomStubs } from "../test-env";
import { FloorPlanViewer, type FloorPlanViewerProps } from "./FloorPlanViewer";

const apartment = apartmentJson as unknown as FloorPlanModel;
const wallId = apartment.walls[0].id;
const wall2 = apartment.walls[1].id;
const roomId = apartment.rooms[0].id;

function Harness({ onChange, ...rest }: Partial<FloorPlanViewerProps> & { onChange?(ids: string[]): void }) {
  const [selection, setSelection] = useState<string[]>([]);
  return (
    <TooltipProvider>
      <FloorPlanViewer
        model={apartment}
        selection={selection}
        onSelectionChange={(ids) => {
          setSelection(ids);
          onChange?.(ids);
        }}
        {...rest}
      />
    </TooltipProvider>
  );
}

const shape = (id: string, container: HTMLElement) => container.querySelector(`[data-layer] [data-element-id="${id}"]`)!;
const canvas = () => screen.getByTestId("floorplan-canvas");
const group = () => screen.getByTestId("view-group");
const scale = () => {
  const m = group().getAttribute("transform")!.match(/scale\((.+)\)/)!;
  return Number(m[1]);
};
const translate = () => group().getAttribute("transform")!.match(/translate\((.+) (.+)\) /)!.slice(1).map(Number);

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  installDomStubs();
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, right: 1000, bottom: 800, width: 1000, height: 800, x: 0, y: 0, toJSON: () => ({}) });
});

const click = (el: Element, init: MouseEventInit = {}) => {
  fireEvent.pointerDown(el, { button: 0, clientX: 10, clientY: 10, ...init });
  fireEvent.pointerUp(el, { button: 0, clientX: 10, clientY: 10, ...init });
};

describe("FloorPlanViewer", () => {
  it("renders walls, rooms and an empty canvas for a null model", () => {
    const { container, rerender } = render(<Harness />);
    expect(shape(wallId, container)).toBeInTheDocument();
    rerender(<Harness model={null} />);
    expect(shape(wallId, container)).toBeNull();
  });

  it("fits the plan on mount", () => {
    render(<Harness />);
    expect(scale()).toBeGreaterThan(0.3);
    expect(scale()).toBeLessThan(1);
  });

  it("selects on click and clears on background click", () => {
    const onChange = vi.fn();
    const { container } = render(<Harness onChange={onChange} />);
    click(shape(wallId, container));
    expect(onChange).toHaveBeenLastCalledWith([wallId]);
    expect(container.querySelector(`[data-highlight="${wallId}"]`)).toBeInTheDocument();
    click(canvas());
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("adds to the selection on shift-click and removes on a second one", () => {
    const onChange = vi.fn();
    const { container } = render(<Harness onChange={onChange} />);
    click(shape(wallId, container));
    click(shape(wall2, container), { shiftKey: true });
    expect(onChange).toHaveBeenLastCalledWith([wallId, wall2]);
    click(shape(wallId, container), { shiftKey: true });
    expect(onChange).toHaveBeenLastCalledWith([wall2]);
  });

  it("highlights on hover via delegation and clears on leave", () => {
    const { container } = render(<Harness />);
    fireEvent.pointerMove(shape(roomId, container), { clientX: 5, clientY: 5 });
    expect(container.querySelector(`[data-highlight="${roomId}"]`)).toBeInTheDocument();
    fireEvent.pointerLeave(canvas());
    expect(container.querySelector(`[data-highlight="${roomId}"]`)).toBeNull();
  });

  it("zooms with the wheel, anchored on the cursor, without a React commit until the gesture ends", () => {
    render(<Harness />);
    const before = scale();
    const [tx, ty] = translate();
    const modelX = (400 - tx) / before;
    const modelY = (300 - ty) / before;
    fireEvent.wheel(canvas(), { deltaY: -200, clientX: 400, clientY: 300 });
    const after = scale();
    expect(after).toBeGreaterThan(before);
    const [nx, ny] = translate();
    expect((400 - nx) / after).toBeCloseTo(modelX, 5);
    expect((300 - ny) / after).toBeCloseTo(modelY, 5);
    expect(screen.getByTestId("zoom").textContent).toBe(`${Math.round(after * 100)}%`);
  });

  it("zooms faster for a trackpad pinch (ctrl+wheel)", () => {
    render(<Harness />);
    const before = scale();
    fireEvent.wheel(canvas(), { deltaY: -10, ctrlKey: true, clientX: 1, clientY: 1 });
    expect(scale() / before).toBeCloseTo(Math.exp(0.1), 5);
  });

  it("pans with space-drag and with the middle button", () => {
    render(<Harness />);
    const [x0, y0] = translate();
    fireEvent.keyDown(window, { key: " " });
    fireEvent.pointerDown(canvas(), { button: 0, clientX: 100, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(canvas(), { clientX: 130, clientY: 80, pointerId: 1 });
    fireEvent.pointerUp(canvas(), { button: 0, clientX: 130, clientY: 80, pointerId: 1 });
    fireEvent.keyUp(window, { key: " " });
    expect(translate()).toEqual([x0 + 30, y0 - 20]);
    fireEvent.pointerDown(canvas(), { button: 1, clientX: 0, clientY: 0, pointerId: 2 });
    fireEvent.pointerMove(canvas(), { clientX: 5, clientY: 5, pointerId: 2 });
    fireEvent.pointerUp(canvas(), { button: 1, clientX: 5, clientY: 5, pointerId: 2 });
    expect(translate()).toEqual([x0 + 35, y0 - 15]);
  });

  it("does not select when releasing a space-drag", () => {
    const onChange = vi.fn();
    const { container } = render(<Harness onChange={onChange} />);
    fireEvent.keyDown(window, { key: " " });
    click(shape(wallId, container));
    expect(onChange).not.toHaveBeenCalled();
  });

  it.each([
    ["+", 1.25],
    ["=", 1.25],
    ["-", 0.8],
  ])("zooms with the %s key", (key, factor) => {
    render(<Harness />);
    const before = scale();
    fireEvent.keyDown(window, { key });
    expect(scale() / before).toBeCloseTo(factor, 5);
  });

  it("resets to 100 % with 0 and fits again with F", () => {
    render(<Harness />);
    const fitted = scale();
    fireEvent.keyDown(window, { key: "0" });
    expect(scale()).toBe(1);
    fireEvent.keyDown(window, { key: "f" });
    expect(scale()).toBe(fitted);
  });

  it("nudges the view with arrow keys", () => {
    render(<Harness />);
    const [x0, y0] = translate();
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(translate()).toEqual([x0 + 48, y0 - 48]);
  });

  it("clears the selection with Escape", () => {
    const onChange = vi.fn();
    const { container } = render(<Harness onChange={onChange} />);
    click(shape(wallId, container));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("ignores shortcuts while typing", () => {
    render(
      <>
        <input data-testid="text" />
        <Harness />
      </>,
    );
    const before = scale();
    fireEvent.keyDown(screen.getByTestId("text"), { key: "+" });
    expect(scale()).toBe(before);
  });

  it("cycles elements of the selected kind with Tab and backwards with Shift+Tab", () => {
    const onChange = vi.fn();
    const { container } = render(<Harness onChange={onChange} />);
    click(shape(wallId, container));
    fireEvent.keyDown(canvas(), { key: "Tab" });
    expect(onChange).toHaveBeenLastCalledWith([wall2]);
    fireEvent.keyDown(canvas(), { key: "Tab", shiftKey: true });
    expect(onChange).toHaveBeenLastCalledWith([wallId]);
  });

  it("leaves Tab alone with no selection so keyboard users can leave the canvas", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    expect(fireEvent.keyDown(canvas(), { key: "Tab" })).toBe(true);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("zooms to an element on double-click", () => {
    const { container } = render(<Harness />);
    const before = scale();
    fireEvent.doubleClick(shape(apartment.doors[0].id, container));
    expect(scale()).toBeGreaterThan(before);
  });

  it("hides a layer without rebuilding the plan", async () => {
    const { container } = render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Layers" }));
    fireEvent.click(await screen.findByRole("switch", { name: "Walls" }));
    expect(container.querySelector('[data-layer="walls"]')).toHaveAttribute("display", "none");
    expect(container.querySelector('[data-layer="rooms"]')).not.toHaveAttribute("display");
  });

  it("disables the original-drawing underlay without an artifact and draws it with one", async () => {
    const { rerender, container } = render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Layers" }));
    expect(await screen.findByRole("switch", { name: "Original drawing" })).toBeDisabled();
    rerender(<Harness underlayUrl="https://example.test/p.png" />);
    fireEvent.click(screen.getByRole("switch", { name: "Original drawing" }));
    expect(container.querySelector("image")).toHaveAttribute("href", "https://example.test/p.png");
    expect(container.querySelector("image")).toHaveAttribute("opacity", "0.55");
  });

  it("shows a metric scale when calibrated and px with a chip when not", () => {
    const { rerender } = render(<Harness />);
    expect(screen.getByTestId("scale-label").textContent).toMatch(/m$/);
    expect(screen.queryByText("Not calibrated")).toBeNull();
    rerender(<Harness model={unscaledJson as unknown as FloorPlanModel} />);
    expect(screen.getByTestId("scale-label").textContent).toMatch(/px$/);
    expect(screen.getByText("Not calibrated")).toBeInTheDocument();
  });

  it("reads coordinates in the honest unit", () => {
    const { rerender } = render(<Harness model={unscaledJson as unknown as FloorPlanModel} />);
    fireEvent.pointerMove(canvas(), { clientX: 100, clientY: 100 });
    expect(screen.getByTestId("coords").textContent).toMatch(/px · .* px$/);
    rerender(<Harness model={apartment} />);
    fireEvent.pointerMove(canvas(), { clientX: 100, clientY: 100 });
    expect(screen.getByTestId("coords").textContent).toMatch(/mm · .* mm$/);
  });

  it("draws the preview ghost in its own layer", () => {
    const after = structuredClone(apartment);
    after.walls[0].start.y += 30;
    after.walls[0].end.y += 30;
    const overlay = previewOverlay({ added: [], modified: [wallId], removed: [] }, apartment, after);
    render(<Harness overlay={overlay} />);
    const layer = screen.getByTestId("preview-layer");
    expect(layer.querySelector('[data-change="modified-before"]')).toHaveAttribute("stroke-dasharray", "6 4");
    expect(layer.querySelector('[data-change="modified-after"]')).not.toHaveAttribute("stroke-dasharray");
  });

  it("re-fits on resize until the user has panned", () => {
    let trigger = () => {};
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(cb: () => void) {
          trigger = cb;
        }
        observe() {}
        disconnect() {}
      },
    );
    render(<Harness />);
    const fitted = scale();
    const rect = (width: number) => vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, right: width, bottom: 800, width, height: 800, x: 0, y: 0, toJSON: () => ({}) });
    rect(500);
    trigger();
    expect(scale()).toBeLessThan(fitted);
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    const panned = scale();
    rect(1400);
    trigger();
    expect(scale()).toBe(panned);

  });
});
