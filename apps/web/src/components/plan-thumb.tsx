"use client";

import { useState } from "react";

import { LogoMark } from "@/components/logo";
import { cn } from "@/lib/utils";

const GRID = {
  backgroundColor: "var(--canvas-paper)",
  backgroundImage: "linear-gradient(var(--canvas-grid) 1px, transparent 1px), linear-gradient(90deg, var(--canvas-grid) 1px, transparent 1px)",
  backgroundSize: "12px 12px",
};

/** A plan thumbnail on drawing paper. Signed URLs expire and new plans have none, so a failed image falls back to blank paper. */
export function PlanThumb({ src, label, className }: { src?: string | null; label?: string; className?: string }) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const show = src && src !== failedSrc;
  return (
    <div style={GRID} className={cn("relative grid shrink-0 place-items-center overflow-hidden rounded-md border", className)}>
      {show ? (
        // Signed storage URLs come from any Supabase host, so next/image's remote allow-list doesn't fit.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={label ?? ""} loading="lazy" onError={() => setFailedSrc(src)} className="size-full bg-(--canvas-paper) object-contain" />
      ) : (
        <LogoMark className="size-5 opacity-30" />
      )}
    </div>
  );
}
