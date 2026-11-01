import { cn } from "@/lib/utils";

/** The mark: a wall corner with a door swing, drawn the way a plan draws it. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden className={cn("size-5 shrink-0", className)}>
      <path d="M3 21V3h18" stroke="currentColor" strokeWidth="3" strokeLinecap="square" />
      <path d="M21 3v8" stroke="var(--primary)" strokeWidth="2" strokeLinecap="square" />
      <path d="M21 11A10 10 0 0 1 11 21" stroke="var(--primary)" strokeWidth="1.5" strokeDasharray="2 2.4" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <LogoMark />
      AEC Studio
    </span>
  );
}
