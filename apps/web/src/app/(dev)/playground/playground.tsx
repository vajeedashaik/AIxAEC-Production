"use client";

import { useTheme } from "next-themes";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { ChangeSet, FloorPlanModel } from "@/contracts";
import { FloorPlanViewer } from "@/features/viewer/components/FloorPlanViewer";
import { previewOverlay } from "@/features/viewer/render/diff";
import apartment from "@/mocks/fixtures/apartment.model.json";
import unscaled from "@/mocks/fixtures/apartment.unscaled.model.json";
import twoRoom from "@/mocks/fixtures/two_room.model.json";

import { syntheticModel } from "./synthetic";

const FIXTURES = {
  apartment: { label: "Apartment (scaled)", model: () => apartment as unknown as FloorPlanModel },
  unscaled: { label: "Apartment (no scale)", model: () => unscaled as unknown as FloorPlanModel },
  twoRoom: { label: "Two rooms", model: () => twoRoom as unknown as FloorPlanModel },
  synthetic: { label: "Synthetic, 500+ elements", model: () => syntheticModel(500) },
} as const;
type FixtureKey = keyof typeof FIXTURES;

/** A local stand-in for a server preview: shift one wall, add a door, remove a window. */
function sampleChange(model: FloorPlanModel): { after: FloorPlanModel; changes: ChangeSet } {
  const after = structuredClone(model);
  const changes: ChangeSet = { added: [], modified: [], removed: [] };
  const wall = after.walls[0];
  if (wall) {
    wall.start.y += 30;
    wall.end.y += 30;
    changes.modified!.push(wall.id);
  }
  const gone = after.windows.shift();
  if (gone) changes.removed!.push(gone.id);
  const door = after.doors[0];
  if (door) {
    const added = { ...door, id: "playground-added-door", bbox: { ...door.bbox, x: door.bbox.x + 120, y: door.bbox.y + 60 } };
    after.doors.push(added);
    changes.added!.push(added.id);
  }
  return { after, changes };
}

export function Playground() {
  const [key, setKey] = useState<FixtureKey>("apartment");
  const [forcePreview, setForcePreview] = useState(false);
  const [selection, setSelection] = useState<string[]>([]);
  const { resolvedTheme, setTheme } = useTheme();
  const model = useMemo(() => FIXTURES[key].model(), [key]);
  const overlay = useMemo(() => {
    if (!forcePreview) return undefined;
    const { after, changes } = sampleChange(model);
    return previewOverlay(changes, model, after);
  }, [forcePreview, model]);
  const elements = model.walls.length + model.rooms.length + model.doors.length + model.windows.length + model.columns.length + model.stairs.length + model.dimensions.length;

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex h-(--topbar-h) shrink-0 flex-wrap items-center gap-3 border-b bg-card px-3 text-ui">
        <h1 className="font-medium">Workspace playground</h1>
        <Select
          value={key}
          onValueChange={(v) => {
            setKey(v as FixtureKey);
            setSelection([]);
          }}
        >
          <SelectTrigger size="sm" aria-label="Fixture" className="w-56 text-ui">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(FIXTURES).map(([k, f]) => (
              <SelectItem key={k} value={k} className="text-ui">
                {f.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="numeric text-micro text-muted-foreground">{elements} elements</span>
        <label className="flex items-center gap-2">
          <Switch size="sm" checked={forcePreview} onCheckedChange={setForcePreview} aria-label="Force preview" /> Preview ghost
        </label>
        <Button size="sm" variant="outline" className="ml-auto" onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
          {resolvedTheme === "dark" ? "Light" : "Dark"} theme
        </Button>
      </header>
      <main className="min-h-0 flex-1">
        <FloorPlanViewer key={key} model={model} selection={selection} onSelectionChange={setSelection} overlay={overlay} />
      </main>
    </div>
  );
}
