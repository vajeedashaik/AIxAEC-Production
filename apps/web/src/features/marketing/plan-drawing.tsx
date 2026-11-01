import { cn } from "@/lib/utils";

import { areaLabel, INITIAL_PLAN, PLAN_H, PLAN_W, planRooms, SPLIT_Y, type MovableWall, type PlanState } from "./plan-geometry";

const EXTERIOR = 140;
const INTERIOR = 90;
const MARGIN = 420; // the viewBox adds 160 more on top, for the dimension label

const wall = (delay: number, width = INTERIOR) => ({
  pathLength: 1,
  stroke: width === EXTERIOR ? "var(--canvas-wall-exterior)" : "var(--canvas-wall)",
  strokeWidth: width,
  strokeLinecap: "square" as const,
  fill: "none",
  className: "plan-wall",
  style: { animationDelay: `${delay}ms` },
});

/** Plain SVG on the frozen --canvas-* palette, so dark mode is "blueprint at night" with no extra work. Renders on the server. */
export function PlanDrawing({
  plan = INITIAL_PLAN,
  ghost,
  highlight = [],
  className,
}: {
  plan?: PlanState;
  /** Candidate state, drawn over the plan as the preview ghost. */
  ghost?: PlanState | null;
  /** Walls offered in a clarification. */
  highlight?: MovableWall[];
  className?: string;
}) {
  const rooms = planRooms(ghost ?? plan);
  const moved = (["kitchen", "bath"] as MovableWall[]).filter((w) => ghost && ghost[w] !== plan[w]);
  const wallY = (w: MovableWall): [number, number] => (w === "kitchen" ? [0, SPLIT_Y] : [SPLIT_Y, PLAN_H]);

  return (
    <svg
      viewBox={`${-MARGIN} ${-MARGIN - 160} ${PLAN_W + MARGIN * 2} ${PLAN_H + MARGIN * 2 + 160}`}
      role="img"
      aria-label="Floor plan of a two-bedroom apartment: living room, kitchen, hall, bath and two bedrooms."
      className={cn("h-auto w-full select-none", className)}
    >
      {rooms.map((r, i) => (
        <rect key={r.id} className="plan-room" x={r.x} y={r.y} width={r.w} height={r.h} fill={`var(--canvas-room-${r.fill})`} style={{ animationDelay: `${700 + i * 70}ms` }} />
      ))}

      {/* Interior walls */}
      <path d={`M0 ${SPLIT_Y}H${PLAN_W}`} {...wall(250)} />
      <path d={`M3400 ${SPLIT_Y}V${PLAN_H}M4800 ${SPLIT_Y}V${PLAN_H}`} {...wall(350)} />
      {!moved.includes("kitchen") && <path d={`M${plan.kitchen} 0V${SPLIT_Y}`} {...wall(300)} />}
      {!moved.includes("bath") && <path d={`M${plan.bath} ${SPLIT_Y}V${PLAN_H}`} {...wall(400)} />}

      {/* Exterior */}
      <path d={`M0 0H${PLAN_W}V${PLAN_H}H0Z`} {...wall(0, EXTERIOR)} />

      {/* Openings: a gap in the wall, a leaf and its swing */}
      <g fill="none">
        <path d={`M3900 ${SPLIT_Y}h800`} stroke="var(--canvas-paper)" strokeWidth={INTERIOR + 20} />
        <path d={`M3900 ${SPLIT_Y}v800`} stroke="var(--canvas-door)" strokeWidth="40" />
        <path d={`M3900 ${SPLIT_Y + 800}A800 800 0 0 0 4700 ${SPLIT_Y}`} stroke="var(--canvas-door-swing)" strokeWidth="20" strokeDasharray="60 50" />
        <path d={`M1600 0h1800M6400 0h1600M${PLAN_W} 1000v1600M1000 ${PLAN_H}h1600`} stroke="var(--canvas-paper)" strokeWidth={EXTERIOR + 20} />
        <path d={`M1600 0h1800M6400 0h1600M${PLAN_W} 1000v1600M1000 ${PLAN_H}h1600`} stroke="var(--canvas-window)" strokeWidth="50" />
      </g>

      {/* A wall offered in a clarification */}
      {highlight.map((w) => {
        const [y1, y2] = wallY(w);
        return <path key={w} d={`M${plan[w]} ${y1}V${y2}`} stroke="var(--canvas-selection)" strokeWidth={INTERIOR + 60} />;
      })}

      {/* Preview ghost: the wall before (dashed) and after (solid), per DESIGN §5 */}
      {moved.map((w) => {
        const [y1, y2] = wallY(w);
        return (
          <g key={w} fill="none" stroke="var(--canvas-preview-modify)">
            <path d={`M${plan[w]} ${y1}V${y2}`} strokeWidth="40" strokeDasharray="110 80" />
            <path d={`M${ghost![w]} ${y1}V${y2}`} strokeWidth={INTERIOR + 20} />
          </g>
        );
      })}

      {rooms.map((r) => (
        <g key={r.id} textAnchor="middle" fontFamily="var(--font-geist-sans)" className="fade-up" style={{ animationDelay: "1100ms" }}>
          <text x={r.x + r.w / 2} y={r.y + r.h / 2 - 40} fill="var(--canvas-room-label)" fontSize="220" fontWeight="500">
            {r.label}
          </text>
          <text x={r.x + r.w / 2} y={r.y + r.h / 2 + 220} fill="var(--canvas-room-area)" fontSize="190" fontFamily="var(--font-geist-mono)">
            {areaLabel(r)}
          </text>
        </g>
      ))}

      {/* Dimension along the top: width of the room the kitchen wall bounds */}
      <g stroke="var(--canvas-dimension)" strokeWidth="16" fill="var(--canvas-dimension)">
        <path d={`M0 -260H${(ghost ?? plan).kitchen}M0 -320V-200M${(ghost ?? plan).kitchen} -320V-200`} fill="none" />
        <text x={(ghost ?? plan).kitchen / 2} y="-310" textAnchor="middle" fontSize="170" stroke="none" fontFamily="var(--font-geist-mono)">
          {(ghost ?? plan).kitchen} mm
        </text>
      </g>
    </svg>
  );
}
