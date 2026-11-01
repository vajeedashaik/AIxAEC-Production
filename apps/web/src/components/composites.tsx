"use client";

import { AlertTriangleIcon, CheckCircle2Icon, CheckIcon, ClockIcon, CopyIcon, Loader2Icon, XCircleIcon, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { JobStatus } from "@/contracts";
import { describeError } from "@/lib/errors";
import { cn } from "@/lib/utils";

export { Kbd, KbdGroup } from "@/components/ui/kbd";

export const ICON_STROKE = 1.5;

/** Title row of a screen. One per screen; the title is the h1. */
export function PageHeader({ title, description, actions, className }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <header className={cn("flex flex-wrap items-start justify-between gap-x-6 gap-y-3", className)}>
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">{title}</h1>
        {description && <p className="mt-1 max-w-[65ch] text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}

/** One sentence and one action (DESIGN §10). */
export function EmptyState({ icon: Icon, title, description, action, className }: { icon?: LucideIcon; title: string; description?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-start gap-3 rounded-lg border border-dashed border-border-strong px-6 py-10", className)}>
      {Icon && <Icon className="size-5 text-muted-foreground" strokeWidth={ICON_STROKE} aria-hidden />}
      <div>
        <h2 className="text-base font-medium">{title}</h2>
        {description && <p className="mt-1 max-w-[60ch] text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/** What happened + retry. Pass the thrown error; copy comes from describeError. */
export function ErrorState({ error, onRetry, title, className }: { error: unknown; onRetry?: () => void; title?: string; className?: string }) {
  const copy = describeError(error);
  return (
    <div role="alert" className={cn("flex flex-col items-start gap-3 rounded-lg border border-border-strong px-6 py-10", className)}>
      <AlertTriangleIcon className="size-5 text-danger" strokeWidth={ICON_STROKE} aria-hidden />
      <div>
        <h2 className="text-base font-medium">{title ?? copy.title}</h2>
        <p className="mt-1 max-w-[60ch] text-sm text-muted-foreground">{copy.description}</p>
      </div>
      {onRetry && copy.retryable && (
        <Button variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** Rows of skeletons. `label` names what is loading for screen readers. */
export function SkeletonList({ rows = 4, rowClassName, label = "Loading", className }: { rows?: number; rowClassName?: string; label?: string; className?: string }) {
  return (
    <div role="status" aria-label={label} className={cn("flex flex-col gap-2", className)}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={cn("h-14 w-full", rowClassName)} />
      ))}
    </div>
  );
}

export function Spinner({ className, label }: { className?: string; label?: string }) {
  return <Loader2Icon role={label ? "status" : undefined} aria-label={label} aria-hidden={label ? undefined : true} strokeWidth={ICON_STROKE} className={cn("size-4 animate-spin motion-reduce:animate-none", className)} />;
}

const STATUS: Record<JobStatus, { label: string; icon: LucideIcon; className: string; spin?: boolean }> = {
  PENDING: { label: "Queued", icon: ClockIcon, className: "text-muted-foreground bg-muted" },
  PROCESSING: { label: "Processing", icon: Loader2Icon, className: "text-info bg-info/10", spin: true },
  COMPLETED: { label: "Ready", icon: CheckCircle2Icon, className: "text-success bg-success/10" },
  FAILED: { label: "Failed", icon: XCircleIcon, className: "text-danger bg-danger/10" },
};

/** Job status: always icon + text, never colour alone. */
export function StatusBadge({ status, className }: { status: JobStatus; className?: string }) {
  const { label, icon: Icon, className: tone, spin } = STATUS[status];
  return (
    <span className={cn("inline-flex h-5 shrink-0 items-center gap-1 rounded-full px-2 text-micro font-medium", tone, className)}>
      <Icon className={cn("size-3", spin && "animate-spin motion-reduce:animate-none")} strokeWidth={2} aria-hidden />
      {label}
    </span>
  );
}

/** Radix handles focus trap, Escape and focus return. `onConfirm` may be async; the dialog stays open until it settles. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  onConfirm,
  destructive = true,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  onConfirm: () => Promise<unknown> | void;
  destructive?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <AlertDialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={busy}
            className={cn(destructive && buttonVariants({ variant: "destructive" }))}
            onClick={async (e) => {
              e.preventDefault(); // keep the dialog open while the work runs
              setBusy(true);
              try {
                await onConfirm();
                onOpenChange(false);
              } catch {
                // the caller reports it (toast); keep the dialog open so the user can retry or cancel
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy && <Spinner />}
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export function CopyButton({ value, label = "Copy", className }: { value: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      className={className}
      aria-label={copied ? "Copied" : label}
      onClick={async () => {
        await navigator.clipboard.writeText(value);
        setCopied(true);
        clearTimeout(timer.current);
        timer.current = setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? <CheckIcon className="text-success" strokeWidth={ICON_STROKE} /> : <CopyIcon strokeWidth={ICON_STROKE} />}
    </Button>
  );
}

/** A figure set as type, not a boxed tile. Zero prints as 0; pass null only while loading. */
export function StatTile({ label, value, detail, className }: { label: string; value: number | string | null; detail?: ReactNode; className?: string }) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-ui text-muted-foreground">{label}</dt>
      <dd className="numeric mt-1 text-2xl font-medium tracking-tight">{value === null ? <Skeleton className="mt-1 h-7 w-12" /> : value}</dd>
      {detail && <dd className="mt-0.5 text-micro text-muted-foreground">{detail}</dd>}
    </div>
  );
}
