"use client";

import { memo, useCallback, useEffect, useImperativeHandle, useMemo, useRef, type PointerEvent as ReactPointerEvent, type ReactNode, type Ref } from "react";

import type { Point } from "@/contracts";

import { pointsAttr } from "../render/svg";
import { LAYERS, tokenVar, type Bounds, type LayerId, type Primitive, type Scene } from "../render/types";
import { centerOn, fitTransform, gridSpacing, IDENTITY, panBy, screenToModel, transformAttr, zoomAt, type Size, type ViewTransform } from "../render/view-transform";

const WHEEL_COMMIT_MS = 120;
const CLICK_SLOP_PX = 4;
const TWEEN_MS = 180;

export const prefersReducedMotion = () =>
  typeof window === "undefined" || !window.matchMedia || window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export interface CanvasHandle {
  /** Fit bounds (default: the whole plan) and forget that the user moved the view. */
  fit(bounds?: Bounds | null): void;
  panTo(point: Point): void;
  panBy(dx: number, dy: number): void;
  zoomBy(factor: number): void;
  /** 100 % centred on the plan. */
  reset(): void;
  transform(): ViewTransform;
  size(): Size;
}

interface Props {
  scene: Scene;
  hiddenLayers: ReadonlySet<LayerId>;
  underlay?: { url: string; opacity: number } | null;
  /** Thin layers drawn above the memoised base, inside the transformed group. */
  children?: ReactNode;
  panMode: boolean;
  /** Fires on every frame of a gesture; must only touch the DOM. */
  onFrame?(t: ViewTransform, size: Size): void;
  /** Fires once per gesture. */
  onCommit?(t: ViewTransform, size: Size): void;
  onPick?(id: string | null, additive: boolean): void;
  onHover?(id: string | null): void;
  onZoomToElement?(id: string): void;
  onPointerModel?(p: Point | null): void;
  ref?: Ref<CanvasHandle>;
  label?: string;
}

/** One primitive as SVG. Base-layer strokes scale with zoom; overlays pass `constant` for screen-space widths. */
export function PrimitiveShape({ p, constant, ...rest }: { p: Primitive; constant?: boolean } & React.SVGProps<SVGElement>) {
  const common = {
    "data-element-id": p.elementId,
    "data-kind": p.kind,
    fill: tokenVar(p.fill),
    fillOpacity: p.opacity,
    stroke: tokenVar(p.stroke),
    strokeWidth: p.strokeWidth,
    strokeDasharray: p.dashed ? "6 4" : undefined,
    vectorEffect: constant ? "non-scaling-stroke" : undefined,
    ...rest,
  } as React.SVGAttributes<SVGElement>;
  switch (p.type) {
    case "polygon":
      return <polygon {...(common as React.SVGAttributes<SVGPolygonElement>)} points={pointsAttr(p.points)} />;
    case "line":
      return <line {...(common as React.SVGAttributes<SVGLineElement>)} x1={p.from[0]} y1={p.from[1]} x2={p.to[0]} y2={p.to[1]} />;
    case "path":
      return <path {...(common as React.SVGAttributes<SVGPathElement>)} d={p.d} />;
    case "text":
      return (
        <text
          {...(common as React.SVGAttributes<SVGTextElement>)}
          x={p.at[0]}
          y={p.at[1]}
          fontSize={p.size}
          fontWeight={p.weight}
          textAnchor="middle"
          fontFamily={p.mono ? "var(--font-geist-mono)" : "var(--font-geist-sans)"}
          style={{ fontVariantNumeric: p.mono ? "tabular-nums slashed-zero" : undefined }}
        >
          {p.text}
        </text>
      );
  }
}

/** Memoised so pan/zoom and hover never re-render the plan. */
const BaseLayer = memo(function BaseLayer({ scene, hiddenLayers }: { scene: Scene; hiddenLayers: ReadonlySet<LayerId> }) {
  return (
    <>
      {LAYERS.map((layer) => (
        <g key={layer} data-layer={layer} display={hiddenLayers.has(layer) ? "none" : undefined} pointerEvents={layer === "labels" ? "none" : undefined}>
          {scene.primitives.map((p, i) => (p.layer === layer ? <PrimitiveShape key={i} p={p} /> : null))}
        </g>
      ))}
    </>
  );
});

function paintGrid(el: HTMLElement | null, t: ViewTransform) {
  if (!el) return;
  const { minor, major } = gridSpacing(t.k);
  el.style.backgroundSize = `${major}px ${major}px, ${major}px ${major}px, ${minor}px ${minor}px, ${minor}px ${minor}px`;
  el.style.backgroundPosition = `${t.x}px ${t.y}px`;
}

/** One SVG with one <g transform>, moved imperatively during gestures so large plans keep 60 fps. */
export function FloorPlanCanvas({ scene, hiddenLayers, underlay, children, panMode, onFrame, onCommit, onPick, onHover, onZoomToElement, onPointerModel, ref, label }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const groupRef = useRef<SVGGElement>(null);
  const view = useRef<ViewTransform>(IDENTITY);
  const size = useRef<Size>({ width: 0, height: 0 });
  const userMoved = useRef(false);
  const callbacks = useRef({ onFrame, onCommit, bounds: scene.bounds });
  useEffect(() => {
    callbacks.current = { onFrame, onCommit, bounds: scene.bounds };
  });
  const tween = useRef<number | null>(null);
  const wheelTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const paint = useCallback((t: ViewTransform) => {
    view.current = t;
    groupRef.current?.setAttribute("transform", transformAttr(t));
    paintGrid(hostRef.current, t);
    callbacks.current.onFrame?.(t, size.current);
  }, []);
  const commit = useCallback(() => callbacks.current.onCommit?.(view.current, size.current), []);

  const stopTween = () => {
    if (tween.current !== null) cancelAnimationFrame(tween.current);
    tween.current = null;
  };

  const flyTo = useCallback(
    (target: ViewTransform) => {
      stopTween();
      if (prefersReducedMotion()) {
        paint(target);
        commit();
        return;
      }
      const from = view.current;
      const start = performance.now();
      const step = (now: number) => {
        const f = Math.min(1, (now - start) / TWEEN_MS);
        const e = 1 - (1 - f) ** 3;
        paint({ k: from.k + (target.k - from.k) * e, x: from.x + (target.x - from.x) * e, y: from.y + (target.y - from.y) * e });
        if (f < 1) tween.current = requestAnimationFrame(step);
        else {
          tween.current = null;
          commit();
        }
      };
      tween.current = requestAnimationFrame(step);
    },
    [commit, paint],
  );

  useImperativeHandle(
    ref,
    () => ({
      fit(bounds) {
        userMoved.current = false;
        flyTo(fitTransform(bounds ?? callbacks.current.bounds, size.current));
      },
      panTo(p) {
        userMoved.current = true;
        flyTo(centerOn(p, size.current, view.current.k));
      },
      panBy(dx, dy) {
        userMoved.current = true;
        stopTween();
        paint(panBy(view.current, dx, dy));
        commit();
      },
      zoomBy(factor) {
        userMoved.current = true;
        stopTween();
        paint(zoomAt(view.current, { x: size.current.width / 2, y: size.current.height / 2 }, factor));
        commit();
      },
      reset() {
        userMoved.current = true;
        const b = callbacks.current.bounds;
        flyTo(centerOn(b ? { x: (b.minX + b.maxX) / 2, y: (b.minY + b.maxY) / 2 } : { x: 0, y: 0 }, size.current, 1));
      },
      transform: () => view.current,
      size: () => size.current,
    }),
    [commit, flyTo, paint],
  );

  // Fit on first layout and on every resize until the user takes over the view.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const measure = () => {
      const { width, height } = host.getBoundingClientRect();
      if (width === size.current.width && height === size.current.height) return;
      size.current = { width, height };
      paint(userMoved.current ? view.current : fitTransform(callbacks.current.bounds, size.current));
      commit();
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(host);
    return () => ro.disconnect();
  }, [commit, paint]);

  // A different plan (not a new version of the same one) gets a fresh fit.
  const planKey = `${scene.width}x${scene.height}`;
  useEffect(() => {
    if (!userMoved.current) {
      paint(fitTransform(callbacks.current.bounds, size.current));
      commit();
    }
  }, [planKey, commit, paint]);

  // React's onWheel is passive; preventing page zoom on pinch needs a native listener.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      stopTween();
      userMoved.current = true;
      const r = host.getBoundingClientRect();
      const factor = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)); // ctrlKey marks a trackpad pinch
      paint(zoomAt(view.current, { x: e.clientX - r.left, y: e.clientY - r.top }, factor));
      if (wheelTimer.current) clearTimeout(wheelTimer.current);
      wheelTimer.current = setTimeout(commit, WHEEL_COMMIT_MS);
    };
    host.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      host.removeEventListener("wheel", onWheel);
      if (wheelTimer.current) clearTimeout(wheelTimer.current);
      stopTween();
    };
  }, [commit, paint]);

  const drag = useRef<{ id: number; x: number; y: number; moved: boolean; panning: boolean } | null>(null);
  const idAt = (target: EventTarget | null) => (target as Element | null)?.closest?.("[data-element-id]")?.getAttribute("data-element-id") ?? null;
  const hoverId = useRef<string | null>(null);
  const setHover = (id: string | null) => {
    if (hoverId.current === id) return;
    hoverId.current = id;
    onHover?.(id);
  };

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    const panning = e.button === 1 || (e.button === 0 && panMode);
    if (e.button !== 0 && !panning) return;
    if (panning) {
      e.preventDefault();
      e.currentTarget.setPointerCapture?.(e.pointerId);
      stopTween();
    }
    drag.current = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false, panning };
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    onPointerModel?.(screenToModel(view.current, { x: e.clientX - r.left, y: e.clientY - r.top }));
    const d = drag.current;
    if (d?.panning) {
      userMoved.current = true;
      d.moved = true;
      paint(panBy(view.current, e.clientX - d.x, e.clientY - d.y));
      d.x = e.clientX;
      d.y = e.clientY;
      return;
    }
    if (d && Math.hypot(e.clientX - d.x, e.clientY - d.y) > CLICK_SLOP_PX) d.moved = true;
    setHover(idAt(e.target));
  };

  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.panning) commit();
    else if (!d.moved) onPick?.(idAt(e.target), e.shiftKey);
  };

  const gridStyle = useMemo(
    () => ({
      backgroundColor: "var(--canvas-paper)",
      backgroundImage: [
        "linear-gradient(var(--canvas-grid-major) 1px, transparent 1px)",
        "linear-gradient(90deg, var(--canvas-grid-major) 1px, transparent 1px)",
        "linear-gradient(var(--canvas-grid) 1px, transparent 1px)",
        "linear-gradient(90deg, var(--canvas-grid) 1px, transparent 1px)",
      ].join(","),
    }),
    [],
  );

  return (
    <div
      ref={hostRef}
      role="application"
      aria-label={label ?? "Floor plan canvas"}
      data-testid="floorplan-canvas"
      tabIndex={0}
      className="absolute inset-0 touch-none overflow-hidden outline-none select-none active:cursor-grabbing focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      style={{ ...gridStyle, cursor: panMode ? "grab" : undefined }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={() => (drag.current = null)}
      onPointerLeave={() => {
        onPointerModel?.(null);
        setHover(null);
      }}
      onDoubleClick={(e) => {
        const id = idAt(e.target);
        if (id) onZoomToElement?.(id);
      }}
    >
      <svg width="100%" height="100%" className="block" role="img" aria-label={label ?? "Floor plan drawing"}>
        <g ref={groupRef} data-testid="view-group">
          {underlay && (
            <image href={underlay.url} x={0} y={0} width={scene.width} height={scene.height} opacity={underlay.opacity} preserveAspectRatio="none" pointerEvents="none" />
          )}
          <BaseLayer scene={scene} hiddenLayers={hiddenLayers} />
          {children}
        </g>
      </svg>
    </div>
  );
}
