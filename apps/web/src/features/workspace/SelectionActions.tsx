"use client";

import { ArrowLeftRight, DoorOpen, PanelTop, PencilLine, Ruler, Scaling, Trash2, type LucideIcon } from "lucide-react";
import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ROOM_TYPES, type CommandInput, type Direction, type Distance, type ResizeMode, type RoomType } from "@/contracts";

import type { ModelElement } from "../viewer/render/geometry";
import { roomTypeName } from "../viewer/render/scene";
import { addDoor, addWindow, deleteDoor, deleteWall, deleteWindow, moveWall, perpendicularDirections, renameRoom, resizeRoom, setScale } from "./commands";

const ALL_DIRECTIONS: Direction[] = ["LEFT", "RIGHT", "UP", "DOWN"];
const dirLabel = (d: string) => d.charAt(0) + d.slice(1).toLowerCase();

function Choice<T extends string>({ label, value, options, onChange, format = dirLabel }: { label: string; value: T; options: readonly T[]; onChange(v: T): void; format?(v: T): string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-micro text-muted-foreground">{label}</span>
      <ToggleGroup type="single" variant="outline" size="sm" aria-label={label} value={value} onValueChange={(v) => v && onChange(v as T)}>
        {options.map((o) => (
          <ToggleGroupItem key={o} value={o}>
            {format(o)}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}

/** A positive number plus a unit. mm needs a scale: px are never passed off as mm. */
function useDistance(hasScale: boolean, defaults: { mm: number; px: number }) {
  const [unit, setUnit] = useState<Distance["unit"]>(hasScale ? "mm" : "px");
  const [raw, setRaw] = useState(String(hasScale ? defaults.mm : defaults.px));
  const value = Number(raw);
  const distance: Distance | null = raw.trim() !== "" && value > 0 && Number.isFinite(value) ? { value, unit } : null;
  return { unit, setUnit, raw, setRaw, distance };
}

function DistanceField({ label, field, hasScale }: { label: string; field: ReturnType<typeof useDistance>; hasScale: boolean }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id} className="text-micro font-normal text-muted-foreground">
        {label}
      </Label>
      <div className="flex gap-1.5">
        <Input id={id} type="number" min={0} step="any" inputMode="decimal" className="numeric h-7 flex-1 text-ui" aria-invalid={!field.distance} value={field.raw} onChange={(e) => field.setRaw(e.target.value)} />
        <ToggleGroup type="single" variant="outline" size="sm" aria-label={`${label} unit`} value={field.unit} onValueChange={(v) => v && field.setUnit(v as Distance["unit"])}>
          <ToggleGroupItem value="mm" disabled={!hasScale}>
            mm
          </ToggleGroupItem>
          <ToggleGroupItem value="px">px</ToggleGroupItem>
        </ToggleGroup>
      </div>
      {!hasScale && <p className="text-micro text-muted-foreground">Set a scale to use mm.</p>}
    </div>
  );
}

function ActionForm({ title, icon: Icon, submit, ready, onSubmit, children, open, onOpenChange }: { title: string; icon: LucideIcon; submit?: string; ready: boolean; onSubmit(): void; children: ReactNode; open?: boolean; onOpenChange?(o: boolean): void }) {
  const [own, setOwn] = useState(false);
  const isOpen = open ?? own;
  const setOpen = (o: boolean) => (onOpenChange ?? setOwn)(o);
  const handle = (e: FormEvent) => {
    e.preventDefault();
    if (!ready) return;
    onSubmit();
    setOpen(false);
  };
  return (
    <Popover open={isOpen} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="justify-start">
          <Icon strokeWidth={1.5} /> {title}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" side="left" className="w-64 p-3">
        <form onSubmit={handle} className="flex flex-col gap-3 text-ui">
          {children}
          <Button type="submit" size="sm" disabled={!ready}>
            {submit ?? "Preview"}
          </Button>
        </form>
      </PopoverContent>
    </Popover>
  );
}

function MoveAction({ id, directions, hasScale, onCommand }: { id: string; directions: Direction[]; hasScale: boolean; onCommand(c: CommandInput): void }) {
  const [direction, setDirection] = useState(directions[0]);
  const dist = useDistance(hasScale, { mm: 300, px: 30 });
  return (
    <ActionForm title="Move" icon={ArrowLeftRight} ready={!!dist.distance} onSubmit={() => onCommand(moveWall(id, direction, dist.distance!))}>
      <Choice<Direction> label="Direction" value={direction} options={directions} onChange={setDirection} />
      <DistanceField label="Distance" field={dist} hasScale={hasScale} />
    </ActionForm>
  );
}

function OpeningAction({ id, kind, hasScale, onCommand }: { id: string; kind: "door" | "window"; hasScale: boolean; onCommand(c: CommandInput): void }) {
  const [position, setPosition] = useState(0.5);
  const dist = useDistance(hasScale, kind === "door" ? { mm: 900, px: 90 } : { mm: 1200, px: 120 });
  const build = kind === "door" ? addDoor : addWindow;
  return (
    <ActionForm title={kind === "door" ? "Add door" : "Add window"} icon={kind === "door" ? DoorOpen : PanelTop} ready={!!dist.distance} onSubmit={() => onCommand(build(id, position, dist.distance))}>
      <div className="flex flex-col gap-1">
        <span className="flex justify-between text-micro text-muted-foreground">
          Position along the wall <span className="numeric">{position.toFixed(2)}</span>
        </span>
        <Slider aria-label="Position along the wall" min={0} max={1} step={0.01} value={[position]} onValueChange={([v]) => setPosition(v)} />
      </div>
      <DistanceField label="Width" field={dist} hasScale={hasScale} />
    </ActionForm>
  );
}

function ScaleAction({ id, requested, onConsumed, onCommand }: { id: string; requested: boolean; onConsumed(): void; onCommand(c: CommandInput): void }) {
  const [open, setOpen] = useState(false);
  const [raw, setRaw] = useState("");
  const value = Number(raw);
  const ready = raw.trim() !== "" && value > 0 && value <= 1_000_000;
  const inputId = useId();
  useEffect(() => {
    if (!requested) return;
    onConsumed();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- a request from outside (rejection, insights CTA) opens the form once
    setOpen(true);
  }, [requested, onConsumed]);
  return (
    <ActionForm title="Set scale" icon={Ruler} open={open} onOpenChange={setOpen} ready={ready} onSubmit={() => onCommand(setScale(id, value))}>
      <div className="flex flex-col gap-1">
        <Label htmlFor={inputId} className="text-micro font-normal text-muted-foreground">
          Real length of this wall (mm)
        </Label>
        <Input id={inputId} autoFocus type="number" min={0} max={1000000} step="any" inputMode="decimal" className="numeric h-7 text-ui" value={raw} onChange={(e) => setRaw(e.target.value)} />
      </div>
    </ActionForm>
  );
}

function RenameAction({ id, name, type, onCommand }: { id: string; name: string; type: RoomType; onCommand(c: CommandInput): void }) {
  const [value, setValue] = useState(name);
  const [roomType, setRoomType] = useState<RoomType>(type);
  const inputId = useId();
  const clean = value.trim();
  return (
    <ActionForm title="Rename" icon={PencilLine} ready={clean.length > 0 && clean.length <= 80} onSubmit={() => onCommand(renameRoom(id, clean, roomType === type ? null : roomType))}>
      <div className="flex flex-col gap-1">
        <Label htmlFor={inputId} className="text-micro font-normal text-muted-foreground">
          Name
        </Label>
        <Input id={inputId} maxLength={80} className="h-7 text-ui" value={value} onChange={(e) => setValue(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-micro text-muted-foreground">Room type</span>
        <Select value={roomType} onValueChange={(v) => setRoomType(v as RoomType)}>
          <SelectTrigger size="sm" aria-label="Room type" className="w-full text-ui">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ROOM_TYPES.map((t) => (
              <SelectItem key={t} value={t} className="text-ui">
                {roomTypeName(t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </ActionForm>
  );
}

function ResizeAction({ id, hasScale, onCommand }: { id: string; hasScale: boolean; onCommand(c: CommandInput): void }) {
  const [direction, setDirection] = useState<Direction>("RIGHT");
  const [mode, setMode] = useState<ResizeMode>("EXPAND");
  const dist = useDistance(hasScale, { mm: 300, px: 30 });
  return (
    <ActionForm title="Resize side" icon={Scaling} ready={!!dist.distance} onSubmit={() => onCommand(resizeRoom(id, direction, dist.distance!, mode))}>
      <Choice<Direction> label="Side" value={direction} options={ALL_DIRECTIONS} onChange={setDirection} />
      <Choice<ResizeMode> label="Mode" value={mode} options={["EXPAND", "CONTRACT"] as const} onChange={setMode} />
      <DistanceField label="Distance" field={dist} hasScale={hasScale} />
    </ActionForm>
  );
}

interface Props {
  entry: ModelElement;
  hasScale: boolean;
  scaleRequested: boolean;
  onScaleConsumed(): void;
  /** Sends the command through the same server preview as typed edits. The client never changes geometry. */
  onCommand(command: CommandInput): void;
}

export function SelectionActions({ entry, hasScale, scaleRequested, onScaleConsumed, onCommand }: Props) {
  const id = entry.element.id;
  const del = (build: (id: string) => CommandInput) => (
    <Button variant="destructive" size="sm" className="justify-start" onClick={() => onCommand(build(id))}>
      <Trash2 strokeWidth={1.5} /> Delete
    </Button>
  );
  let actions: ReactNode = null;
  if (entry.kind === "wall")
    actions = (
      <>
        <MoveAction id={id} directions={perpendicularDirections(entry.element)} hasScale={hasScale} onCommand={onCommand} />
        <OpeningAction id={id} kind="door" hasScale={hasScale} onCommand={onCommand} />
        <OpeningAction id={id} kind="window" hasScale={hasScale} onCommand={onCommand} />
        <ScaleAction id={id} requested={scaleRequested} onConsumed={onScaleConsumed} onCommand={onCommand} />
        {del(deleteWall)}
      </>
    );
  else if (entry.kind === "room")
    actions = (
      <>
        <RenameAction id={id} name={entry.element.label_text ?? ""} type={entry.element.room_type} onCommand={onCommand} />
        <ResizeAction id={id} hasScale={hasScale} onCommand={onCommand} />
      </>
    );
  else if (entry.kind === "door") actions = del(deleteDoor);
  else if (entry.kind === "window") actions = del(deleteWindow);
  if (!actions) return null;
  // Keyed so a form never carries values over to the next element.
  return (
    <div key={id} className="grid grid-cols-2 gap-1.5" data-testid="selection-actions">
      {actions}
    </div>
  );
}
