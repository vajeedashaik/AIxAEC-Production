"use client";

import { CircleAlert, CornerDownLeft, Loader2, Mic, Minus, Pencil, Plus, Square, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Candidate, RejectStage } from "@/contracts";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

import { isTyping } from "../viewer/components/FloorPlanViewer";
import type { Flow } from "./use-command-flow";
import { useVoiceRecorder } from "./use-voice-recorder";

const EXAMPLES = [
  "Move the wall between the kitchen and the living room 300 mm left",
  "Delete the door in the bathroom",
  "Rename the hall to Entry",
  "Add a window to the north wall of the bedroom",
  "Make the bedroom 200 mm wider to the right",
];
const EXAMPLE_MS = 4000;
const MOD = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";

/** Friendly heading per pipeline stage; the server's detail says what to do about it. */
export const REJECT_TITLES: Record<RejectStage, string> = {
  parse: "I didn't understand that",
  schema: "That edit isn't complete",
  entity_resolution: "I couldn't find that element",
  semantic_validation: "That edit doesn't apply here",
  geometry: "The geometry doesn't work",
  constraints: "That would break the plan",
};

interface Props {
  flow: Flow;
  text: string;
  onTextChange(text: string): void;
  disabled?: boolean;
  /** Past instructions, newest first. */
  history: readonly string[];
  hasScale: boolean;
  onPreview(instruction: string): void;
  onApplyInstruction(instruction: string): void;
  onApply(): void;
  onDiscard(): void;
  onPick(candidate: Candidate): void;
  onCandidateFocus(candidate: Candidate | null): void;
  onSetScale(): void;
  /** Upload recorded audio; resolves with the transcript. */
  onAudio(audio: Blob): Promise<string>;
  onVoiceError(error: unknown): void;
}

function ChangeCount({ icon: Icon, count, label, token }: { icon: typeof Plus; count: number; label: string; token: string }) {
  if (!count) return null;
  return (
    <span className="numeric inline-flex items-center gap-1 text-micro" style={{ color: `var(--${token})` }}>
      <Icon className="size-3" strokeWidth={1.5} aria-hidden /> {count} {label}
    </span>
  );
}

/** The hero interaction: one line of intent, a preview of its effect, then Apply. */
export function CommandBar({ flow, text, onTextChange, disabled, history, hasScale, onPreview, onApplyInstruction, onApply, onDiscard, onPick, onCandidateFocus, onSetScale, onAudio, onVoiceError }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const meter = useRef<HTMLSpanElement>(null);
  const [example, setExample] = useState(0);
  const [cursor, setCursor] = useState(-1);
  const [draft, setDraft] = useState("");
  const [heard, setHeard] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);

  const { status, start, stop } = useVoiceRecorder({
    onError: setMicError,
    onLevel: (l) => {
      if (meter.current) meter.current.style.transform = `scaleY(${Math.max(0.08, l)})`;
    },
    onRecorded: async (audio) => {
      setTranscribing(true);
      try {
        const transcript = await onAudio(audio);
        onTextChange(transcript);
        setHeard(true);
        input.current?.focus();
      } catch (e) {
        onVoiceError(e);
        if (!(e instanceof ApiError)) setMicError("I couldn't transcribe that. Try again, or type instead.");
      } finally {
        setTranscribing(false);
      }
    },
  });
  const recording = status === "recording" || status === "starting";

  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setExample((i) => (i + 1) % EXAMPLES.length), EXAMPLE_MS);
    return () => clearInterval(t);
  }, []);

  // "/" focuses from anywhere; holding V talks.
  useEffect(() => {
    const down = (e: globalThis.KeyboardEvent) => {
      if (e.defaultPrevented || isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey || disabled) return;
      if (e.key === "/") {
        e.preventDefault();
        input.current?.focus();
      } else if ((e.key === "v" || e.key === "V") && !e.repeat) {
        e.preventDefault();
        setMicError(null);
        void start();
      }
    };
    const up = (e: globalThis.KeyboardEvent) => {
      if (e.key === "v" || e.key === "V") stop();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [disabled, start, stop]);

  const previewing = flow.state === "preview";
  const busy = flow.state === "busy" || transcribing;
  const clean = text.trim();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (clean && !busy && !disabled) onPreview(clean);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      if (busy || disabled) return;
      if (previewing) onApply();
      else if (clean) onApplyInstruction(clean);
    } else if (e.key === "ArrowUp" && history.length) {
      e.preventDefault();
      if (cursor < 0) setDraft(text);
      const next = Math.min(cursor + 1, history.length - 1);
      setCursor(next);
      onTextChange(history[next]);
    } else if (e.key === "ArrowDown" && cursor >= 0) {
      e.preventDefault();
      const next = cursor - 1;
      setCursor(next);
      onTextChange(next < 0 ? draft : history[next]);
    }
  };

  const res = flow.state === "preview" ? flow.response : null;

  return (
    <div className="pointer-events-none absolute inset-x-3 bottom-14 z-10 flex flex-col items-center gap-2 @2xl:bottom-3">
      <div className="pointer-events-auto flex w-full max-w-[560px] flex-col overflow-hidden rounded-lg border bg-popover shadow-md @2xl:max-w-[min(560px,calc(100%-340px))]" data-testid="command-bar">
        {res && (
          <div className="flex items-start gap-3 border-b p-3" data-testid="preview-card" aria-live="polite">
            <div className="min-w-0 flex-1">
              <p className="text-ui font-medium">{res.summary ?? "Preview ready"}</p>
              <p className="mt-0.5 flex flex-wrap gap-x-3">
                <ChangeCount icon={Plus} count={res.changes?.added?.length ?? 0} label="added" token="canvas-preview-add" />
                <ChangeCount icon={Pencil} count={res.changes?.modified?.length ?? 0} label="modified" token="canvas-preview-modify" />
                <ChangeCount icon={Minus} count={res.changes?.removed?.length ?? 0} label="removed" token="canvas-preview-remove" />
              </p>
            </div>
            <Button size="sm" variant="ghost" onClick={onDiscard}>
              Discard
            </Button>
            <Button size="sm" onClick={onApply}>
              Apply
            </Button>
          </div>
        )}

        {flow.state === "clarification" && (
          <div className="border-b p-3" data-testid="clarification" aria-live="polite">
            <div className="flex items-start justify-between gap-2">
              <p className="text-ui font-medium">{flow.question}</p>
              <Button size="icon-xs" variant="ghost" aria-label="Dismiss" onClick={onDiscard}>
                <X strokeWidth={1.5} />
              </Button>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {flow.candidates.map((c) => (
                <Button
                  key={c.id}
                  size="sm"
                  variant="outline"
                  className="h-auto max-w-full py-1 text-left whitespace-normal"
                  onPointerEnter={() => onCandidateFocus(c)}
                  onPointerLeave={() => onCandidateFocus(null)}
                  onFocus={() => onCandidateFocus(c)}
                  onBlur={() => onCandidateFocus(null)}
                  onClick={() => {
                    onCandidateFocus(null);
                    onPick(c);
                  }}
                >
                  {c.label}
                </Button>
              ))}
            </div>
          </div>
        )}

        {flow.state === "rejected" && (
          <div className="flex items-start gap-2 border-b p-3" data-testid="rejection" role="alert" data-stage={flow.stage}>
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" strokeWidth={1.5} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="text-ui font-medium">{REJECT_TITLES[flow.stage]}</p>
              <p className="text-ui text-muted-foreground">{flow.detail}</p>
            </div>
            {!hasScale && /scale|millimet|\bmm\b/i.test(flow.detail) && (
              <Button size="sm" variant="outline" onClick={onSetScale}>
                Set scale
              </Button>
            )}
            <Button size="icon-xs" variant="ghost" aria-label="Dismiss" onClick={onDiscard}>
              <X strokeWidth={1.5} />
            </Button>
          </div>
        )}

        {flow.state === "stale" && (
          <p className="border-b p-3 text-ui" role="status" data-testid="stale">
            The plan changed; here&apos;s the latest. Your text is still below.
          </p>
        )}

        {(flow.state === "error" || micError) && (
          <p className="flex items-start gap-2 border-b p-3 text-ui" role="alert" data-testid="command-error">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" strokeWidth={1.5} aria-hidden />
            {flow.state === "error" ? flow.message : micError}
          </p>
        )}

        {heard && !res && clean && (
          <p className="px-3 pt-2 text-micro text-muted-foreground" data-testid="heard">
            Heard: edit if needed, then press Enter to preview.
          </p>
        )}

        <form onSubmit={submit} className="flex h-(--command-bar-h) items-center gap-2 px-2">
          <Input
            ref={input}
            aria-label="Describe an edit"
            value={text}
            disabled={disabled}
            maxLength={500}
            onChange={(e) => {
              setCursor(-1);
              setHeard(false);
              onTextChange(e.target.value);
            }}
            onKeyDown={onKeyDown}
            placeholder={disabled ? "Viewing an old version: go back to HEAD to edit" : recording ? "Listening…" : EXAMPLES[example]}
            className="h-8 min-w-0 flex-1 border-0 bg-transparent px-1 text-ui shadow-none focus-visible:ring-0 dark:bg-transparent"
          />
          {recording && (
            <span className="flex h-5 w-1.5 items-end overflow-hidden rounded-sm bg-muted" aria-hidden>
              <span ref={meter} data-testid="level-meter" className="h-full w-full origin-bottom scale-y-[0.08] bg-primary" />
            </span>
          )}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="icon-sm"
                variant={recording ? "destructive" : "ghost"}
                aria-label={recording ? "Stop recording" : "Speak an edit"}
                aria-pressed={recording}
                disabled={disabled || transcribing}
                onClick={() => {
                  setMicError(null);
                  if (recording) stop();
                  else void start();
                }}
              >
                {transcribing ? <Loader2 className="animate-spin" strokeWidth={1.5} /> : recording ? <Square strokeWidth={1.5} /> : <Mic strokeWidth={1.5} />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Click to record, or hold <span className="numeric">V</span> · 60 s max
            </TooltipContent>
          </Tooltip>
          <span aria-live="polite" className="sr-only">
            {flow.state === "busy" ? flow.label : ""}
          </span>
          {flow.state === "busy" ? (
            <Loader2 className="size-4 animate-spin text-muted-foreground" strokeWidth={1.5} aria-hidden />
          ) : (
            <span className={cn("hidden items-center gap-1 text-micro text-muted-foreground @xl:inline-flex", !clean && "opacity-60")}>
              <Kbd>
                <CornerDownLeft strokeWidth={1.5} />
              </Kbd>
              preview
              <Kbd className="numeric ml-1">{MOD}↵</Kbd>
              apply
            </span>
          )}
        </form>
      </div>
    </div>
  );
}
