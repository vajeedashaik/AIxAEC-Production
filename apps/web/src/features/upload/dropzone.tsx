"use client";

import { AlertTriangleIcon, CheckIcon, RotateCcwIcon, UploadIcon, XIcon } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { ICON_STROKE } from "@/components/composites";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useUploadQueue, type UploadItem } from "./use-upload-queue";
import { ACCEPT } from "./validate";

function QueueRow({ item, onRetry, onRemove }: { item: UploadItem; onRetry: () => void; onRemove: () => void }) {
  const percent = Math.round(item.progress * 100);
  const bad = item.status === "failed" || item.status === "rejected";
  return (
    <li className="py-2">
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-ui font-medium">{item.file.name}</span>
        <span className="numeric shrink-0 text-micro text-muted-foreground">{formatBytes(item.file.size)}</span>
        <span className="numeric w-16 shrink-0 text-right text-micro text-muted-foreground" aria-live="polite">
          {item.status === "queued" && "queued"}
          {item.status === "uploading" && `${percent}%`}
          {item.status === "done" && <CheckIcon aria-label="Uploaded" className="ml-auto size-3.5 text-success" strokeWidth={2} />}
          {bad && <span className="text-danger">{item.status === "rejected" ? "rejected" : "failed"}</span>}
        </span>
        {item.status === "failed" && (
          <Button variant="ghost" size="icon-sm" aria-label={`Retry ${item.file.name}`} onClick={onRetry}>
            <RotateCcwIcon strokeWidth={ICON_STROKE} />
          </Button>
        )}
        <Button variant="ghost" size="icon-sm" aria-label={item.status === "uploading" ? `Cancel ${item.file.name}` : `Dismiss ${item.file.name}`} onClick={onRemove}>
          <XIcon strokeWidth={ICON_STROKE} />
        </Button>
      </div>
      {item.status === "uploading" && <Progress value={percent} aria-label={`Uploading ${item.file.name}`} className="mt-1.5 h-1" />}
      {item.error && (
        <p role="alert" className="mt-1 text-ui text-danger">
          {item.error}
        </p>
      )}
      {item.warnings.map((w) => (
        <p key={w} className="mt-1 flex items-start gap-1.5 text-ui text-warning">
          <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" strokeWidth={2} aria-hidden />
          {w}
        </p>
      ))}
    </li>
  );
}

export function UploadDropzone({ projectId, className }: { projectId: string; className?: string }) {
  const { items, add, retry, remove } = useUploadQueue(projectId);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    add(e.dataTransfer.files);
  };

  return (
    <section aria-label="Upload floor plans" className={className}>
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-border-strong bg-surface-sunken px-4 py-5 transition-colors duration-(--duration-fast) hover:border-ring focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ring",
          over && "border-ring bg-primary/5",
        )}
      >
        <UploadIcon className="size-5 shrink-0 text-muted-foreground" strokeWidth={ICON_STROKE} aria-hidden />
        <span className="min-w-0">
          <span className="block text-sm font-medium">Drop floor plans here, or browse files</span>
          <span className="block text-ui text-muted-foreground">PNG, JPG or PDF, up to 25 MB each. Processing starts after upload.</span>
        </span>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          aria-label="Choose floor plan files"
          className="sr-only"
          onChange={(e) => {
            add(e.target.files ?? []);
            if (input.current) input.current.value = ""; // so the same file can be picked again
          }}
        />
      </label>
      {items.length > 0 && (
        <ul aria-label="Upload queue" className="mt-2 divide-y">
          {items.map((item) => (
            <QueueRow key={item.id} item={item} onRetry={() => retry(item.id)} onRemove={() => remove(item.id)} />
          ))}
        </ul>
      )}
    </section>
  );
}
