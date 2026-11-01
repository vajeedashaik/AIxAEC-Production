"use client";

import { ChevronRight, Copy, History as HistoryIcon, MousePointerClick, PencilLine, Scan, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { roomFillVar, type CommandInput, type EditLogEntry, type FloorPlanModel, type History, type Insights, type RoomType, type Source } from "@/contracts";
import { cn } from "@/lib/utils";

import { describeElement, elementLabel } from "../viewer/render/describe";
import { indexElements, type ModelElement } from "../viewer/render/geometry";
import { roomTypeName } from "../viewer/render/scene";
import { formatPx, formatPx2 } from "../viewer/render/units";
import { SelectionActions } from "./SelectionActions";

const rowClass = "flex h-8 w-full min-w-0 items-center gap-1.5 rounded-md px-2 text-left text-ui hover:bg-muted [.density-compact_&]:h-7";

/* ── Outline ──────────────────────────────────────────────────────────────── */

interface OutlineProps {
  model: FloorPlanModel;
  selection: readonly string[];
  onPick(id: string): void;
}

function OutlineRow({ entry, depth, selected, onPick, leading }: { entry: ModelElement; depth: number; selected: boolean; onPick(id: string): void; leading?: React.ReactNode }) {
  return (
    <button type="button" className={cn(rowClass, selected && "bg-accent font-medium text-accent-foreground")} style={{ paddingLeft: 8 + depth * 16 }} aria-current={selected || undefined} onClick={() => onPick(entry.element.id)}>
      {leading}
      <span className="truncate">{elementLabel(entry)}</span>
    </button>
  );
}

/** Rooms → their walls and openings, then everything no room claims. */
export function Outline({ model, selection, onPick }: OutlineProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set());
  const { tree, others } = useMemo(() => {
    const index = indexElements(model);
    const claimed = new Set<string>();
    const tree = model.rooms.map((room) => {
      claimed.add(room.id);
      const walls = new Set(room.wall_ids);
      const children = [
        ...room.wall_ids.flatMap((id) => index.get(id) ?? []),
        ...model.doors.filter((d) => d.wall_id && walls.has(d.wall_id)).map((element): ModelElement => ({ kind: "door", element })),
        ...model.windows.filter((d) => d.wall_id && walls.has(d.wall_id)).map((element): ModelElement => ({ kind: "window", element })),
      ];
      for (const c of children) claimed.add(c.element.id);
      return { entry: { kind: "room", element: room } as ModelElement, children };
    });
    return { tree, others: [...index.values()].filter((e) => !claimed.has(e.element.id)) };
  }, [model]);

  const q = query.trim().toLowerCase();
  const hit = (e: ModelElement) => elementLabel(e).toLowerCase().includes(q) || e.kind.includes(q);
  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const rooms = tree.filter((t) => !q || hit(t.entry) || t.children.some(hit));
  const rest = others.filter((e) => !q || hit(e));

  return (
    <div className="flex h-full flex-col" aria-label="Plan outline">
      <div className="relative shrink-0 border-b p-2">
        <Search className="pointer-events-none absolute top-1/2 left-4 size-3.5 -translate-y-1/2 text-muted-foreground" strokeWidth={1.5} aria-hidden />
        <Input aria-label="Search elements" placeholder="Search elements" className="h-7 pl-7 text-ui" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-px p-2">
          {rooms.map(({ entry, children }) => {
            const expanded = !!q || open.has(entry.element.id) || children.some((c) => selection.includes(c.element.id));
            const shown = q ? children.filter(hit) : children;
            return (
              <div key={entry.element.id}>
                <div className="flex items-center">
                  <Button variant="ghost" size="icon-xs" className="shrink-0" aria-label={`${expanded ? "Collapse" : "Expand"} ${elementLabel(entry)}`} aria-expanded={expanded} onClick={() => toggle(entry.element.id)}>
                    <ChevronRight className={cn("transition-transform duration-(--duration-fast)", expanded && "rotate-90")} strokeWidth={1.5} />
                  </Button>
                  <OutlineRow entry={entry} depth={0} selected={selection.includes(entry.element.id)} onPick={onPick} />
                </div>
                {expanded && shown.map((c) => <OutlineRow key={c.element.id} entry={c} depth={1.5} selected={selection.includes(c.element.id)} onPick={onPick} />)}
              </div>
            );
          })}
          {rest.length > 0 && <p className="px-2 pt-3 pb-1 text-micro text-muted-foreground">Other elements</p>}
          {rest.map((e) => (
            <OutlineRow key={e.element.id} entry={e} depth={0} selected={selection.includes(e.element.id)} onPick={onPick} />
          ))}
          {q && !rooms.length && !rest.length && <p className="p-2 text-ui text-muted-foreground">Nothing matches “{query}”.</p>}
        </div>
      </ScrollArea>
    </div>
  );
}

/* ── Inspector ────────────────────────────────────────────────────────────── */

const SOURCE_LABEL: Record<Source, string> = { DETECTED: "Detected", INFERRED: "Inferred", USER_CONFIRMED: "Confirmed" };
function SourceBadge({ source, confidence }: { source: Source; confidence?: number | null }) {
  return (
    <Badge variant={source === "USER_CONFIRMED" ? "secondary" : "outline"} className="font-normal" data-source={source}>
      {SOURCE_LABEL[source]}
      {confidence != null && <span className="numeric text-muted-foreground">{Math.round(confidence * 100)}%</span>}
    </Badge>
  );
}

interface InspectorProps {
  model: FloorPlanModel;
  selection: readonly string[];
  readOnly: boolean;
  scaleRequested: boolean;
  onScaleConsumed(): void;
  onPick(id: string): void;
  onCommand(command: CommandInput): void;
}

export function Inspector({ model, selection, readOnly, scaleRequested, onScaleConsumed, onPick, onCommand }: InspectorProps) {
  const index = useMemo(() => indexElements(model), [model]);
  const hasScale = !!model.coordinate_system.mm_per_pixel;

  if (!selection.length) {
    return (
      <div className="flex flex-col gap-2 p-4 text-ui" data-testid="inspector-empty">
        <MousePointerClick className="size-5 text-muted-foreground" strokeWidth={1.5} aria-hidden />
        {scaleRequested ? <p className="font-medium">Click a wall whose real length you know.</p> : <p className="text-muted-foreground">Select an element on the plan to measure it and edit it.</p>}
      </div>
    );
  }
  if (selection.length > 1) {
    return (
      <div className="flex flex-col gap-1 p-4 text-ui">
        <p className="font-medium">
          <span className="numeric">{selection.length}</span> elements selected
        </p>
        {selection.flatMap((id) => index.get(id) ?? []).map((e) => (
          <button key={e.element.id} type="button" className={rowClass} onClick={() => onPick(e.element.id)}>
            <span className="truncate">{elementLabel(e)}</span>
          </button>
        ))}
      </div>
    );
  }
  const entry = index.get(selection[0]);
  const d = describeElement(model, selection[0]);
  if (!entry || !d) return null;

  return (
    <div className="flex flex-col gap-4 p-4 text-ui" data-testid="inspector">
      <div className="flex flex-col gap-1.5">
        <h2 className="text-base font-medium">{d.title}</h2>
        <div className="flex flex-wrap items-center gap-1.5">
          <SourceBadge source={d.source} confidence={d.confidence} />
        </div>
        <button
          type="button"
          className="numeric group flex w-fit max-w-full items-center gap-1 text-micro text-muted-foreground hover:text-foreground"
          aria-label="Copy element id"
          onClick={() => navigator.clipboard?.writeText(d.id).then(() => toast.success("Copied element id"), () => toast.error("Couldn't copy"))}
        >
          <span className="truncate">{d.id}</span>
          <Copy className="size-3 shrink-0" strokeWidth={1.5} aria-hidden />
        </button>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        {d.facts.map((f) => (
          <div key={f.label} className="col-span-2 grid grid-cols-subgrid">
            <dt className="text-muted-foreground">{f.label}</dt>
            <dd className="numeric text-right">
              {f.value}
              {f.metric && <span className="block text-micro text-muted-foreground">{f.metric}</span>}
            </dd>
          </div>
        ))}
        {d.roomType && (
          <div className="col-span-2 grid grid-cols-subgrid items-center">
            <dt className="text-muted-foreground">Type</dt>
            <dd className="flex items-center justify-end gap-1.5">
              {roomTypeName(d.roomType.type)}
              {d.roomType.source && <SourceBadge source={d.roomType.source} confidence={d.roomType.confidence} />}
            </dd>
          </div>
        )}
      </dl>

      {!readOnly && <SelectionActions entry={entry} hasScale={hasScale} scaleRequested={scaleRequested} onScaleConsumed={onScaleConsumed} onCommand={onCommand} />}

      {d.links.length > 0 && (
        <div className="flex flex-col gap-px">
          <h3 className="pb-1 text-micro text-muted-foreground">Linked</h3>
          {d.links.map((l) => (
            <button key={l.id} type="button" className={cn(rowClass, "-mx-2 w-auto")} onClick={() => onPick(l.id)}>
              <span className="truncate">{l.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Insights ─────────────────────────────────────────────────────────────── */

function Stat({ label, value, metric }: { label: string; value: string; metric?: string | null }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="numeric text-right">
        {metric ?? value}
        {metric && <span className="block text-micro text-muted-foreground">{value}</span>}
      </dd>
    </div>
  );
}

export function InsightsPanel({ insights, onCalibrate, readOnly }: { insights: Insights; onCalibrate(): void; readOnly: boolean }) {
  const { counts, metric: m } = insights;
  const byType = Object.entries(insights.rooms_by_type)
    .filter((e): e is [string, number] => !!e[1])
    .sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...byType.map(([, n]) => n));
  const m2 = (v: number | undefined) => (v === undefined ? null : `${v} m²`);
  const lm = (v: number | undefined) => (v === undefined ? null : `${v} m`);
  const refLabel = (r: Insights["largest_room"]) => (r ? r.label ?? "Unnamed room" : "None");
  return (
    <div className="flex flex-col gap-5 p-4 text-ui" data-testid="insights">
      {!m && (
        <div className="flex items-center justify-between gap-3 rounded-md border p-3">
          <p className="text-muted-foreground">Calibrate to see m².</p>
          {!readOnly && (
            <Button size="sm" variant="outline" onClick={onCalibrate}>
              Set scale
            </Button>
          )}
        </div>
      )}
      <section className="flex flex-col gap-1">
        <h2 className="pb-1 text-micro text-muted-foreground">Areas</h2>
        <dl className="flex flex-col gap-1">
          <Stat label="Total" value={formatPx2(insights.total_area_px)} metric={m2(m?.total_area_m2)} />
          <Stat label="Average room" value={formatPx2(insights.average_room_area_px)} metric={m2(m?.average_room_area_m2)} />
          <Stat label={`Largest: ${refLabel(insights.largest_room)}`} value={insights.largest_room ? formatPx2(insights.largest_room.area_px) : "None"} />
          <Stat label={`Smallest: ${refLabel(insights.smallest_room)}`} value={insights.smallest_room ? formatPx2(insights.smallest_room.area_px) : "None"} />
        </dl>
      </section>
      <section className="flex flex-col gap-1">
        <h2 className="pb-1 text-micro text-muted-foreground">Walls</h2>
        <dl className="flex flex-col gap-1">
          <Stat label="Total" value={formatPx(insights.total_wall_length_px)} metric={lm(m?.total_wall_length_m)} />
          <Stat label="Exterior" value={formatPx(insights.exterior_wall_length_px)} metric={lm(m?.exterior_wall_length_m)} />
          <Stat label="Interior" value={formatPx(insights.interior_wall_length_px)} metric={lm(m?.interior_wall_length_m)} />
        </dl>
      </section>
      <section className="flex flex-col gap-1">
        <h2 className="pb-1 text-micro text-muted-foreground">Rooms by type</h2>
        <ul className="flex flex-col gap-1">
          {byType.map(([type, n]) => (
            <li key={type} className="grid grid-cols-[6rem_1fr_1.5rem] items-center gap-2">
              <span className="truncate text-muted-foreground">{roomTypeName(type)}</span>
              <span className="h-3 rounded-sm border" style={{ width: `${(n / max) * 100}%`, background: roomFillVar(type as RoomType), borderColor: "var(--canvas-room-stroke)" }} />
              <span className="numeric text-right">{n}</span>
            </li>
          ))}
          {!byType.length && <li className="text-muted-foreground">No rooms detected.</li>}
        </ul>
      </section>
      <section className="flex flex-col gap-1">
        <h2 className="pb-1 text-micro text-muted-foreground">Counts</h2>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
          {Object.entries(counts).map(([k, v]) => (
            <div key={k} className="flex justify-between">
              <dt className="text-muted-foreground capitalize">{k}</dt>
              <dd className="numeric">{v}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}

/* ── History ──────────────────────────────────────────────────────────────── */

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const opLabel = (op: string | null) => (op ? roomTypeName(op) : null);
const STATUS_CLASS: Record<EditLogEntry["status"], string> = {
  APPLIED: "text-success",
  REJECTED: "text-danger",
  CLARIFICATION: "text-warning",
  UNDO: "text-muted-foreground",
  REDO: "text-muted-foreground",
};

export function HistoryPanel({ history, loading, viewing, onView }: { history: History | undefined; loading: boolean; viewing: number | null; onView(version: number | null): void }) {
  if (loading || !history) {
    return (
      <div className="flex flex-col gap-2 p-4" data-testid="history-loading">
        <Skeleton className="h-8" />
        <Skeleton className="h-8" />
        <Skeleton className="h-8" />
      </div>
    );
  }
  const versions = [...history.versions].sort((a, b) => b.version - a.version);
  return (
    <div className="flex flex-col gap-5 p-4 text-ui" data-testid="history">
      <section>
        <h2 className="pb-1 text-micro text-muted-foreground">Versions</h2>
        <ol className="flex flex-col gap-px">
          {versions.map((v) => {
            const Icon = v.origin === "PROCESSING" ? Scan : PencilLine;
            const current = viewing === v.version || (viewing === null && v.is_head);
            return (
              <li key={v.version}>
                <button
                  type="button"
                  className={cn(rowClass, current && "bg-accent text-accent-foreground", v.discarded && "text-muted-foreground opacity-60")}
                  aria-current={current || undefined}
                  data-discarded={v.discarded || undefined}
                  onClick={() => onView(v.is_head ? null : v.version)}
                >
                  <Icon className="size-3.5 shrink-0" strokeWidth={1.5} aria-label={v.origin === "PROCESSING" ? "From processing" : "From an edit"} />
                  <span className="numeric">v{v.version}</span>
                  {v.is_head && <Badge variant="secondary" className="h-4 px-1.5 text-micro font-normal">HEAD</Badge>}
                  {v.discarded && <span className="text-micro">discarded</span>}
                  <span className="numeric ml-auto text-micro text-muted-foreground">{time(v.created_at)}</span>
                </button>
              </li>
            );
          })}
        </ol>
      </section>
      <section>
        <h2 className="pb-1 text-micro text-muted-foreground">Edit log</h2>
        {history.edits.length === 0 && (
          <p className="flex items-center gap-2 text-muted-foreground">
            <HistoryIcon className="size-4" strokeWidth={1.5} aria-hidden /> No edits yet. Your first one shows up here.
          </p>
        )}
        <ol className="flex flex-col gap-2">
          {history.edits.map((e) => (
            <li key={e.id} className="flex flex-col gap-0.5 border-b pb-2 last:border-b-0" data-testid="edit-entry">
              <span className="flex items-center justify-between gap-2 text-micro">
                <span className={STATUS_CLASS[e.status]}>
                  {roomTypeName(e.status)}
                  {e.stage && ` · ${e.stage.replace(/_/g, " ")}`}
                </span>
                <span className="numeric text-muted-foreground">{time(e.created_at)}</span>
              </span>
              <span className="line-clamp-2">{e.instruction ?? opLabel(e.operation) ?? (e.result_version != null ? `Moved to v${e.result_version}` : "Edit")}</span>
              {e.error && <span className="text-micro text-muted-foreground">{e.error}</span>}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

