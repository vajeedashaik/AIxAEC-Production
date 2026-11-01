"use client";

import { useId, useState, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";

export const CAPABILITIES = [
  { name: "Detect", body: "Walls, rooms, doors, windows, columns, stairs and text become typed elements, each with its source and confidence.", keys: ["D"] },
  { name: "Edit by text", body: "Ten operations in plain language: move a wall, resize a room, add a door, set the scale. You see a preview ghost before anything is saved.", keys: ["E"] },
  { name: "Edit by voice", body: "Say the instruction. You see what it heard, then the same preview, through the same pipeline as typing.", keys: ["V"] },
  { name: "Undo anything", body: "Every edit creates an immutable version. Undo and redo move between them, and the full history stays readable.", keys: ["⌘", "Z"] },
  { name: "Read the insights", body: "Areas, wall lengths and rooms by type come from the model. Without a known scale they stay in pixels, because pixels are never passed off as millimetres.", keys: ["I"] },
];

/** The capabilities set as the product's own command menu: type to filter, arrows to move. */
export function CapabilityList() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(CAPABILITIES[0].name);
  const listId = useId();
  const shown = CAPABILITIES.filter((c) => `${c.name} ${c.body}`.toLowerCase().includes(query.trim().toLowerCase()));
  const active = shown.find((c) => c.name === selected) ?? shown[0];

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const i = shown.findIndex((c) => c === active);
    const next = shown[(i + (e.key === "ArrowDown" ? 1 : shown.length - 1)) % shown.length];
    if (next) setSelected(next.name);
  };

  return (
    <div data-ui>
      <input
        type="text"
        role="combobox"
        aria-expanded
        aria-controls={listId}
        aria-activedescendant={active ? `${listId}-${active.name}` : undefined}
        aria-label="Filter capabilities"
        placeholder="What it does"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
        className="h-[1.9em] w-full rounded-md bg-accent px-3 text-[clamp(1.25rem,2.4vw,2.25rem)] font-medium tracking-tight outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
      />
      <ul id={listId} role="listbox" aria-label="Capabilities" className="mt-3 flex flex-col gap-1">
        {shown.map((c) => {
          const on = c === active;
          return (
            // Keyboard selection lives on the combobox above, per the ARIA combobox pattern.
            <li key={c.name} id={`${listId}-${c.name}`} role="option" aria-selected={on} onClick={() => setSelected(c.name)} onMouseEnter={() => setSelected(c.name)} className={cn("cursor-default rounded-md px-3 py-2 transition-colors duration-(--duration-instant)", on && "bg-primary text-primary-foreground")}>
              <div className="flex items-center justify-between gap-4">
                <span className="text-[clamp(1.75rem,3.6vw,3.25rem)] leading-[1.15] font-medium tracking-tight">{c.name}</span>
                <span aria-hidden className="flex gap-1 max-sm:hidden">
                  {c.keys.map((k) => (
                    <kbd key={k} className={cn("grid size-8 place-items-center rounded-md font-sans text-sm", on ? "bg-primary-foreground/15" : "bg-accent text-muted-foreground")}>
                      {k}
                    </kbd>
                  ))}
                </span>
              </div>
              {on && <p className="max-w-[60ch] pt-1 pb-1 text-base">{c.body}</p>}
            </li>
          );
        })}
        {shown.length === 0 && <li className="px-3 py-4 text-base text-muted-foreground">Nothing by that name. Try “wall” or “undo”.</li>}
      </ul>
    </div>
  );
}
