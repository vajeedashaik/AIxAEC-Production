"use client";

import { ImageIcon, Layers, Maximize, Minus, Plus } from "lucide-react";
import { memo, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type ReactNode, type Ref } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { FloorPlanModel, Point } from "@/contracts";

import { boundsOf, elementOutline, indexElements, round2 } from "../render/geometry";
import { buildScene } from "../render/scene";
import { pointsAttr } from "../render/svg";
import { LAYERS, type Bounds, type LayerId, type OverlayPrimitive, type Scene } from "../render/types";
import { formatMm, scaleBar } from "../render/units";
import type { Size, ViewTransform } from "../render/view-transform";
import { FloorPlanCanvas, prefersReducedMotion, PrimitiveShape, type CanvasHandle } from "./FloorPlanCanvas";

const LAYER_LABELS: Record<LayerId, string> = {
  rooms: "Rooms",
  walls: "Walls",
  openings: "Openings",
  objects: "Objects",
  dimensions: "Dimensions",
  labels: "Labels",
};
const ZOOM_STEP = 1.25;
const NUDGE_PX = 48;
const PULSE_MS = 1200;
const MINIMAP_W = 148;

export const isTyping = (t: EventTarget | null) => {
  const el = t as HTMLElement | null;
  return !!el?.closest?.("input, textarea, select, [contenteditable=true], [role=combobox], [role=slider], [role=menu], [role=listbox], [role=dialog]");
};

export interface ViewerHandle {
  zoomToElement(id: string): void;
  panToPoint(p: Point): void;
}

export interface FloorPlanViewerProps {
  model: FloorPlanModel | null | undefined;
  selection: readonly string[];
  onSelectionChange(ids: string[]): void;
  /** Preview ghost. */
  overlay?: readonly OverlayPrimitive[];
  /** Externally highlighted elements, e.g. a clarification candidate under the pointer. */
  highlightIds?: readonly string[];
  /** Elements that just changed; pulse once. */
  pulseIds?: readonly string[];
  underlayUrl?: string | null;
  /** Floating UI above the canvas (the command bar). */
  children?: ReactNode;
  readOnly?: boolean;
  ref?: Ref<ViewerHandle>;
}

function outlinePoints(index: ReturnType<typeof indexElements>, id: string) {
  return elementOutline(index.get(id));
}

function Highlight({ index, ids, token, fill }: { index: ReturnType<typeof indexElements>; ids: readonly string[]; token: string; fill?: string }) {
  return (
    <g pointerEvents="none">
      {ids.map((id) => {
        const pts = outlinePoints(index, id);
        return pts ? (
          <polygon key={id} points={pointsAttr(pts)} fill={fill ?? "none"} stroke={`var(--${token})`} strokeWidth={1.5} vectorEffect="non-scaling-stroke" data-highlight={id} />
        ) : null;
      })}
    </g>
  );
}

const Minimap = memo(function Minimap({ scene, onNavigate, rectRef }: { scene: Scene; onNavigate(p: Point): void; rectRef: Ref<SVGRectElement> }) {
  const b = scene.bounds;
  if (!b) return null;
  const pad = 40;
  const vb = { x: b.minX - pad, y: b.minY - pad, w: b.maxX - b.minX + pad * 2, h: b.maxY - b.minY + pad * 2 };
  const toModel = (e: React.PointerEvent<SVGSVGElement>): Point => {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: vb.x + ((e.clientX - r.left) / r.width) * vb.w, y: vb.y + ((e.clientY - r.top) / r.height) * vb.h };
  };
  return (
    <svg
      data-testid="minimap"
      viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
      width={MINIMAP_W}
      height={(MINIMAP_W * vb.h) / vb.w}
      className="block cursor-pointer rounded-md border bg-(--canvas-paper) shadow-sm"
      aria-hidden
      onPointerDown={(e) => {
        e.stopPropagation();
        e.currentTarget.setPointerCapture?.(e.pointerId);
        onNavigate(toModel(e));
      }}
      onPointerMove={(e) => {
        if (e.buttons === 1) onNavigate(toModel(e));
      }}
    >
      {scene.primitives.map((p, i) => (p.layer === "rooms" || p.layer === "walls" ? <PrimitiveShape key={i} p={p} /> : null))}
      <rect ref={rectRef} fill="var(--canvas-selection-fill)" stroke="var(--canvas-selection)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
});

function ToolButton({ label, kbd, onClick, children }: { label: string; kbd?: string; onClick(): void; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={label} onClick={onClick}>
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {label}
        {kbd && <span className="numeric ml-2 opacity-70">{kbd}</span>}
      </TooltipContent>
    </Tooltip>
  );
}

/** The interactive plan: transform, hover and layer state live here; the model and selection are props. */
export function FloorPlanViewer({ model, selection, onSelectionChange, overlay, highlightIds, pulseIds, underlayUrl, children, readOnly, ref }: FloorPlanViewerProps) {
  const canvas = useRef<CanvasHandle>(null);
  const scene = useMemo(() => buildScene(model), [model]);
  const index = useMemo(() => indexElements(model), [model]);
  const mpp = model?.coordinate_system.mm_per_pixel;

  const [view, setView] = useState<{ t: ViewTransform; size: Size }>({ t: { k: 1, x: 0, y: 0 }, size: { width: 0, height: 0 } });
  const [hover, setHover] = useState<string | null>(null);
  const [hidden, setHidden] = useState<ReadonlySet<LayerId>>(() => new Set());
  const [underlayOn, setUnderlayOn] = useState(false);
  const [underlayOpacity, setUnderlayOpacity] = useState(0.55);
  const [panMode, setPanMode] = useState(false);

  const zoomLabel = useRef<HTMLSpanElement>(null);
  const barEl = useRef<HTMLDivElement>(null);
  const barLabel = useRef<HTMLSpanElement>(null);
  const miniRect = useRef<SVGRectElement>(null);
  const coord = useRef<HTMLOutputElement>(null);

  // Imperative twin of the committed readouts, so chrome tracks gestures without React renders.
  const paintChrome = useCallback(
    (t: ViewTransform, size: Size) => {
      if (zoomLabel.current) zoomLabel.current.textContent = `${Math.round(t.k * 100)}%`;
      const bar = scaleBar(t.k, mpp);
      if (barEl.current) barEl.current.style.width = `${bar.widthPx}px`;
      if (barLabel.current) barLabel.current.textContent = bar.label;
      miniRect.current?.setAttribute("x", String(-t.x / t.k));
      miniRect.current?.setAttribute("y", String(-t.y / t.k));
      miniRect.current?.setAttribute("width", String(size.width / t.k));
      miniRect.current?.setAttribute("height", String(size.height / t.k));
    },
    [mpp],
  );
  useEffect(() => paintChrome(view.t, view.size), [paintChrome, view]);

  const zoomToBounds = useCallback((b: Bounds | null) => {
    if (!b) return;
    const pad = Math.max(b.maxX - b.minX, b.maxY - b.minY, 80) * 0.6;
    canvas.current?.fit({ minX: b.minX - pad, minY: b.minY - pad, maxX: b.maxX + pad, maxY: b.maxY + pad });
  }, []);
  const zoomToElement = useCallback(
    (id: string) => {
      const pts = outlinePoints(index, id);
      if (pts) zoomToBounds(boundsOf(pts));
    },
    [index, zoomToBounds],
  );
  useImperativeHandle(ref, () => ({ zoomToElement, panToPoint: (p) => canvas.current?.panTo(p) }), [zoomToElement]);

  const onPick = useCallback(
    (id: string | null, additive: boolean) => {
      if (!id) {
        if (!additive) onSelectionChange([]);
        return;
      }
      if (additive) onSelectionChange(selection.includes(id) ? selection.filter((s) => s !== id) : [...selection, id]);
      else onSelectionChange([id]);
    },
    [onSelectionChange, selection],
  );

  const onCommit = useCallback((t: ViewTransform, size: Size) => setView({ t, size }), []);
  const onPointerModel = useCallback(
    (p: Point | null) => {
      if (!coord.current) return;
      if (!p) {
        coord.current.textContent = "";
        return;
      }
      const x = formatMm(p.x, mpp);
      coord.current.textContent = x ? `${x} · ${formatMm(p.y, mpp)}` : `${round2(p.x)} px · ${round2(p.y)} px`;
    },
    [mpp],
  );

  // Latest values for the window listener without re-subscribing on every selection change.
  const keyState = useRef({ selection, onSelectionChange, index });
  useEffect(() => {
    keyState.current = { selection, onSelectionChange, index };
  });

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented || isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      const c = canvas.current;
      if (!c) return;
      const act = (fn: () => void) => {
        e.preventDefault();
        fn();
      };
      switch (e.key) {
        case " ":
          return act(() => setPanMode(true));
        case "f":
        case "F":
          return act(() => c.fit());
        case "0":
          return act(() => c.reset());
        case "+":
        case "=":
          return act(() => c.zoomBy(ZOOM_STEP));
        case "-":
        case "_":
          return act(() => c.zoomBy(1 / ZOOM_STEP));
        case "ArrowLeft":
          return act(() => c.panBy(NUDGE_PX, 0));
        case "ArrowRight":
          return act(() => c.panBy(-NUDGE_PX, 0));
        case "ArrowUp":
          return act(() => c.panBy(0, NUDGE_PX));
        case "ArrowDown":
          return act(() => c.panBy(0, -NUDGE_PX));
        case "Escape":
          if (keyState.current.selection.length) act(() => keyState.current.onSelectionChange([]));
          return;
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key === " ") setPanMode(false);
    };
    const onBlur = () => setPanMode(false);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
    };
  }, []);

  // Tab cycles within the selected kind only while the canvas has focus and something is selected; Esc releases it.
  const onHostKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== "Tab" || !selection.length) return;
    const current = index.get(selection[selection.length - 1]);
    if (!current) return;
    const peers = [...index.values()].filter((v) => v.kind === current.kind).map((v) => v.element.id);
    const at = peers.indexOf(current.element.id);
    const next = peers[(at + (e.shiftKey ? -1 : 1) + peers.length) % peers.length];
    e.preventDefault();
    onSelectionChange([next]);
    zoomIntoViewIfNeeded(next);
  };
  const zoomIntoViewIfNeeded = (id: string) => {
    const b = boundsOf(outlinePoints(index, id) ?? []);
    if (b) canvas.current?.panTo({ x: (b.minX + b.maxX) / 2, y: (b.minY + b.maxY) / 2 });
  };

  const pulseRef = useRef<SVGGElement>(null);
  const pulseKey = pulseIds?.join() ?? "";
  useEffect(() => {
    if (!pulseKey || prefersReducedMotion()) return;
    pulseRef.current?.animate?.([{ opacity: 1 }, { opacity: 0.25 }, { opacity: 1 }, { opacity: 0 }], { duration: PULSE_MS, easing: "ease-out", fill: "forwards" });
  }, [pulseKey]);

  const toggleLayer = (l: LayerId, on: boolean) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (on) next.delete(l);
      else next.add(l);
      return next;
    });

  const initialBar = scaleBar(view.t.k, mpp);
  const underlay = underlayOn && underlayUrl ? { url: underlayUrl, opacity: underlayOpacity } : null;

  return (
    <div className="@container relative h-full w-full overflow-hidden" onKeyDown={onHostKeyDown} data-read-only={readOnly || undefined}>
      <FloorPlanCanvas
        ref={canvas}
        scene={scene}
        hiddenLayers={hidden}
        underlay={underlay}
        panMode={panMode}
        onFrame={paintChrome}
        onCommit={onCommit}
        onPick={onPick}
        onHover={setHover}
        onZoomToElement={zoomToElement}
        onPointerModel={onPointerModel}
      >
        {selection.length > 0 && <Highlight index={index} ids={selection} token="canvas-selection" fill="var(--canvas-selection-fill)" />}
        {hover && !selection.includes(hover) && <Highlight index={index} ids={[hover]} token="canvas-hover" />}
        {highlightIds && highlightIds.length > 0 && <Highlight index={index} ids={highlightIds} token="canvas-selection" fill="var(--canvas-selection-fill)" />}
        {overlay && overlay.length > 0 && (
          <g data-testid="preview-layer" pointerEvents="none">
            {overlay.map((p, i) => (
              <PrimitiveShape key={i} p={p} constant data-change={p.change} />
            ))}
          </g>
        )}
        {pulseIds && pulseIds.length > 0 && (
          <g ref={pulseRef} data-testid="pulse-layer">
            <Highlight index={index} ids={pulseIds} token="canvas-selection" fill="var(--canvas-selection-fill)" />
          </g>
        )}
      </FloorPlanCanvas>

      {/* Top-left: layers */}
      <div className="absolute top-3 left-3 flex items-center gap-2">
        <Popover>
          <Tooltip>
            <TooltipTrigger asChild>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="bg-card" aria-label="Layers">
                  <Layers strokeWidth={1.5} /> Layers
                </Button>
              </PopoverTrigger>
            </TooltipTrigger>
            <TooltipContent>Show or hide parts of the plan</TooltipContent>
          </Tooltip>
          <PopoverContent align="start" className="w-60 gap-1 p-3 text-ui">
            {LAYERS.map((l) => (
              <div key={l} className="flex h-7 items-center justify-between">
                <Label htmlFor={`layer-${l}`} className="font-normal">
                  {LAYER_LABELS[l]}
                </Label>
                <Switch id={`layer-${l}`} size="sm" checked={!hidden.has(l)} onCheckedChange={(on) => toggleLayer(l, on)} />
              </div>
            ))}
            <div className="mt-2 border-t pt-2">
              <div className="flex h-7 items-center justify-between">
                <Label htmlFor="layer-underlay" className="font-normal">
                  <ImageIcon className="size-3.5" strokeWidth={1.5} /> Original drawing
                </Label>
                <Switch id="layer-underlay" size="sm" disabled={!underlayUrl} checked={underlayOn} onCheckedChange={setUnderlayOn} />
              </div>
              {underlayOn && underlayUrl && (
                <Slider className="mt-2" aria-label="Original drawing opacity" min={0.1} max={1} step={0.05} value={[underlayOpacity]} onValueChange={([v]) => setUnderlayOpacity(v)} />
              )}
              {!underlayUrl && <p className="mt-1 text-micro text-muted-foreground">No processed image for this plan.</p>}
            </div>
          </PopoverContent>
        </Popover>
        {scene.skipped > 0 && (
          <Badge variant="outline" className="bg-card text-warning">
            {scene.skipped} skipped: invalid geometry
          </Badge>
        )}
      </div>

      {/* Bottom-left: scale bar + coordinates */}
      <div className="pointer-events-none absolute bottom-3 left-3 flex flex-col-reverse items-start gap-1">
        <div className="flex flex-col gap-1 rounded-md border bg-card px-2 py-1 shadow-sm">
          <div className="flex items-center gap-2">
            <span ref={barLabel} data-testid="scale-label" className="numeric text-micro">
              {initialBar.label}
            </span>
            {!mpp && <span className="text-micro text-warning">Not calibrated</span>}
          </div>
          <div ref={barEl} data-testid="scale-bar" className="h-1 border-x border-b border-foreground" style={{ width: initialBar.widthPx }} />
        </div>
        <output ref={coord} data-testid="coords" className="numeric hidden text-micro text-muted-foreground @2xl:block" />
      </div>

      {/* Bottom-right: minimap + zoom */}
      <div className="absolute right-3 bottom-3 flex flex-col items-end gap-2">
        <div className="hidden @2xl:block">
          <Minimap scene={scene} rectRef={miniRect} onNavigate={(p) => canvas.current?.panTo(p)} />
        </div>
        <div className="flex items-center rounded-md border bg-card shadow-sm">
          <ToolButton label="Zoom out" kbd="-" onClick={() => canvas.current?.zoomBy(1 / ZOOM_STEP)}>
            <Minus strokeWidth={1.5} />
          </ToolButton>
          <span ref={zoomLabel} data-testid="zoom" className="numeric w-11 text-center text-micro">
            {Math.round(view.t.k * 100)}%
          </span>
          <ToolButton label="Zoom in" kbd="+" onClick={() => canvas.current?.zoomBy(ZOOM_STEP)}>
            <Plus strokeWidth={1.5} />
          </ToolButton>
          <ToolButton label="Fit plan" kbd="F" onClick={() => canvas.current?.fit()}>
            <Maximize strokeWidth={1.5} />
          </ToolButton>
        </div>
      </div>

      {children}
    </div>
  );
}
