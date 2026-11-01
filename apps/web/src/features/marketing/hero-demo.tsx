"use client";

import { AlertTriangleIcon, CheckIcon, CornerDownLeftIcon, HelpCircleIcon, RotateCcwIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { PlanDrawing } from "./plan-drawing";
import { INITIAL_PLAN, moveWallLeft, type MovableWall, type PlanState } from "./plan-geometry";

type Outcome =
  | { kind: "idle" }
  | { kind: "preview"; ghost: PlanState; summary: string }
  | { kind: "clarify"; mm: number }
  | { kind: "rejected"; detail: string }
  | { kind: "applied"; summary: string };

const COMMANDS = [
  { text: "move the kitchen wall 300 mm left", wall: "kitchen" as MovableWall | null, mm: 300 },
  { text: "move the wall 300 mm left", wall: null, mm: 300 },
  { text: "move the kitchen wall 5000 mm left", wall: "kitchen" as MovableWall | null, mm: 5000 },
];
const CANDIDATES: { wall: MovableWall; label: string }[] = [
  { wall: "kitchen", label: "Between living room and kitchen" },
  { wall: "bath", label: "Between bath and bedroom 2" },
];
const TYPE_MS = 28;
const AUTOPLAY_DELAY_MS = 1500;

/** The hero's working fragment: the same outcomes as the real pipeline (preview, clarification, rejection, undo), on a tiny real calculation. */
export function HeroDemo() {
  const [versions, setVersions] = useState<PlanState[]>([INITIAL_PLAN]);
  const [typed, setTyped] = useState(COMMANDS[0].text);
  const [outcome, setOutcome] = useState<Outcome>({ kind: "idle" });
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const plan = versions.at(-1)!;

  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };

  const interpret = useCallback(
    (wall: MovableWall | null, mm: number) => {
      if (!wall) return setOutcome({ kind: "clarify", mm });
      const result = moveWallLeft(plan, wall, mm);
      setOutcome(result.ok ? { kind: "preview", ghost: result.plan, summary: result.summary } : { kind: "rejected", detail: result.detail });
    },
    [plan],
  );

  const run = useCallback(
    (command: (typeof COMMANDS)[number]) => {
      clearTimers();
      setOutcome({ kind: "idle" });
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        setTyped(command.text);
        return interpret(command.wall, command.mm);
      }
      setTyped("");
      [...command.text].forEach((_, i) => timers.current.push(setTimeout(() => setTyped(command.text.slice(0, i + 1)), i * TYPE_MS)));
      timers.current.push(setTimeout(() => interpret(command.wall, command.mm), command.text.length * TYPE_MS + 250));
    },
    [interpret],
  );

  // Plays once after the walls draw in, then waits for the visitor. Static text already reads correctly before this runs.
  useEffect(() => {
    const t = setTimeout(() => run(COMMANDS[0]), AUTOPLAY_DELAY_MS);
    return () => {
      clearTimeout(t);
      clearTimers();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on mount
  }, []);

  const apply = (ghost: PlanState, summary: string) => {
    setVersions((v) => [...v, ghost]);
    setOutcome({ kind: "applied", summary });
  };
  const undo = () => {
    setVersions((v) => v.slice(0, -1));
    setOutcome({ kind: "idle" });
  };

  return (
    <div data-ui className="flex w-full max-w-2xl flex-col gap-3">
      <div className="flex items-center justify-between gap-3 text-ui">
        <span className="font-medium">apartment.png</span>
        <span className="numeric rounded-sm border bg-card px-1.5 text-micro leading-5 text-muted-foreground">v{versions.length} · HEAD</span>
      </div>

      <PlanDrawing plan={plan} ghost={outcome.kind === "preview" ? outcome.ghost : null} highlight={outcome.kind === "clarify" ? CANDIDATES.map((c) => c.wall) : []} />

      <div className="flex flex-col gap-2 rounded-lg border bg-card p-2 shadow-md">
        <div className="flex h-8 items-center gap-2 px-1 text-sm">
          <span aria-label="Command" className="min-w-0 flex-1 truncate">
            {typed}
            <span aria-hidden className="ml-px inline-block h-4 w-px translate-y-0.5 bg-primary" />
          </span>
          <CornerDownLeftIcon className="size-3.5 shrink-0 text-muted-foreground" strokeWidth={1.5} aria-hidden />
        </div>

        {/* min-h holds the layout still as outcomes change */}
        <div aria-live="polite" className="min-h-[4.25rem] border-t px-1 pt-2 text-ui">
          {outcome.kind === "idle" && <p className="text-muted-foreground">{versions.length > 1 ? "Undone. The earlier version is untouched." : "Try one of the commands below."}</p>}
          {outcome.kind === "preview" && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="min-w-0 flex-1 basis-56">
                <span className="font-medium text-warning">Preview.</span> {outcome.summary}
              </p>
              <div className="flex gap-1.5">
                <Button size="sm" variant="ghost" onClick={() => setOutcome({ kind: "idle" })}>
                  Discard
                </Button>
                <Button size="sm" onClick={() => apply(outcome.ghost, outcome.summary)}>
                  Apply
                </Button>
              </div>
            </div>
          )}
          {outcome.kind === "applied" && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="flex min-w-0 flex-1 basis-56 items-start gap-1.5">
                <CheckIcon className="mt-0.5 size-3.5 shrink-0 text-success" strokeWidth={2} aria-hidden />
                <span>
                  {outcome.summary} Saved as <span className="numeric">v{versions.length}</span>.
                </span>
              </p>
              <Button size="sm" variant="outline" onClick={undo}>
                <RotateCcwIcon strokeWidth={1.5} />
                Undo
              </Button>
            </div>
          )}
          {outcome.kind === "clarify" && (
            <div>
              <p className="flex items-center gap-1.5">
                <HelpCircleIcon className="size-3.5 shrink-0 text-info" strokeWidth={2} aria-hidden />
                Which wall do you mean? It doesn&apos;t guess.
              </p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {CANDIDATES.map((c) => (
                  <Button key={c.wall} size="sm" variant="outline" onClick={() => interpret(c.wall, outcome.mm)}>
                    {c.label}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {outcome.kind === "rejected" && (
            <p className="flex items-start gap-1.5">
              <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0 text-danger" strokeWidth={2} aria-hidden />
              <span>
                <span className="font-medium text-danger">Rejected by the geometry engine.</span> {outcome.detail} Nothing changed.
              </span>
            </p>
          )}
        </div>
      </div>

      <div role="group" aria-label="Example commands" className="flex flex-wrap gap-1.5">
        {COMMANDS.map((c) => (
          <button
            key={c.text}
            type="button"
            onClick={() => run(c)}
            aria-pressed={typed === c.text}
            className={cn("min-h-8 rounded-md border bg-card px-2.5 py-1 text-left text-ui transition-colors duration-(--duration-instant) hover:border-border-strong", typed === c.text ? "border-border-strong font-medium" : "text-muted-foreground")}
          >
            {c.text}
          </button>
        ))}
      </div>
    </div>
  );
}
