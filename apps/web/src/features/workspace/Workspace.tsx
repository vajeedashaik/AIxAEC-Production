"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Download, FileQuestion, History as HistoryIcon, Loader2, PanelRight, Redo2, RotateCw, ScanSearch, Undo2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Artifact, Candidate, CommandInput, CommandResponse, FloorPlan, Furniture, FurniturePlacement, ModelEnvelope } from "@/contracts";
import { ApiError, queryKeys, useApi } from "@/lib/api";
import { cn } from "@/lib/utils";

import { FloorPlanViewer, isTyping, type ViewerHandle } from "../viewer/components/FloorPlanViewer";
import { previewOverlay } from "../viewer/render/diff";
import { indexElements } from "../viewer/render/geometry";
import { CommandBar } from "./CommandBar";
import { AnalyzePanel } from "./analysis";
import { AskPanel } from "./ask";
import { HistoryPanel, Inspector, InsightsPanel, Outline } from "./panels";
import { useCommandFlow, type CommandSource } from "./use-command-flow";

const PULSE_CLEAR_MS = 1400;
const POLL_MS = 2000;
const MOD = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl+";

type RightTab = "inspect" | "insights" | "analyze" | "ask" | "history" | "outline";

const wideQuery = "(min-width: 1024px)";
function useWide() {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia?.(wideQuery);
      m?.addEventListener("change", cb);
      return () => m?.removeEventListener("change", cb);
    },
    () => window.matchMedia?.(wideQuery).matches ?? true,
    () => true,
  );
}

function IconAction({ label, kbd, disabled, active, onClick, children }: { label: string; kbd?: string; disabled?: boolean; active?: boolean; onClick(): void; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {/* Wrapper keeps the tooltip alive on a disabled button. */}
        <span className="inline-flex">
          <Button variant={active ? "secondary" : "ghost"} size="icon-sm" aria-label={label} aria-pressed={active} disabled={disabled} onClick={onClick}>
            {children}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {label}
        {kbd && <span className="numeric ml-2 opacity-70">{kbd}</span>}
      </TooltipContent>
    </Tooltip>
  );
}

function StatusBadge({ status }: { status: FloorPlan["status"] }) {
  const tone = { PENDING: "text-info", PROCESSING: "text-info", COMPLETED: "text-success", FAILED: "text-danger" }[status];
  const text = { PENDING: "Queued", PROCESSING: "Processing", COMPLETED: "Processed", FAILED: "Failed" }[status];
  return (
    <Badge variant="outline" className={cn("hidden font-normal sm:inline-flex", tone)} data-testid="status">
      {text}
    </Badge>
  );
}

function Message({ icon, title, children, action }: { icon: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center bg-(--canvas-paper) p-6">
      <div className="flex max-w-sm flex-col gap-2 text-ui" data-testid="workspace-message">
        <span className="text-muted-foreground">{icon}</span>
        <h1 className="text-base font-medium">{title}</h1>
        {children && <div className="text-muted-foreground">{children}</div>}
        {action && <div className="mt-2 flex gap-2">{action}</div>}
      </div>
    </div>
  );
}

export function CanvasSkeleton() {
  return (
    <div className="flex h-full" data-testid="canvas-skeleton" aria-busy aria-label="Loading plan">
      <div className="hidden w-60 flex-col gap-2 border-r p-3 lg:flex">
        <Skeleton className="h-7" />
        <Skeleton className="h-6" />
        <Skeleton className="h-6" />
        <Skeleton className="h-6" />
      </div>
      <div className="flex-1 bg-(--canvas-paper) p-10">
        <Skeleton className="h-full w-full opacity-50" />
      </div>
      <div className="hidden w-(--inspector-w) flex-col gap-2 border-l p-4 lg:flex">
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-4" />
        <Skeleton className="h-4" />
      </div>
    </div>
  );
}

export interface WorkspaceProps {
  projectId: string;
  floorplanId: string;
  /** From ?version=; null means HEAD. */
  version: number | null;
  onVersionChange(version: number | null): void;
}

export function Workspace({ projectId, floorplanId, version, onVersionChange }: WorkspaceProps) {
  const api = useApi();
  const qc = useQueryClient();
  const keys = queryKeys.floorplans;
  const wide = useWide();

  const floorplan = useQuery({
    queryKey: keys.detail(floorplanId),
    queryFn: ({ signal }) => api.getFloorplan(floorplanId, signal),
    refetchInterval: (q) => (q.state.data && (q.state.data.status === "PENDING" || q.state.data.status === "PROCESSING") ? POLL_MS : false),
  });
  const ready = floorplan.data?.current_model_version != null;
  const head = useQuery({
    queryKey: keys.model(floorplanId),
    queryFn: ({ signal }) => api.getModel(floorplanId, undefined, signal),
    enabled: ready,
    placeholderData: keepPreviousData,
  });
  const pinned = useQuery({
    queryKey: keys.model(floorplanId, version ?? undefined),
    queryFn: ({ signal }) => api.getModel(floorplanId, version!, signal),
    enabled: ready && version !== null,
    staleTime: Infinity, // versions are immutable
  });
  const history = useQuery({ queryKey: keys.history(floorplanId), queryFn: ({ signal }) => api.getHistory(floorplanId, signal), enabled: ready });
  const artifacts = useQuery({ queryKey: keys.artifacts(floorplanId), queryFn: ({ signal }) => api.listArtifacts(floorplanId, signal), enabled: ready });

  const headVersion = head.data?.version ?? null;
  const readOnly = version !== null && version !== headVersion;
  const envelope: ModelEnvelope | undefined = version !== null ? pinned.data : head.data;
  const model = envelope?.model ?? null;
  const index = useMemo(() => indexElements(model), [model]);

  const viewer = useRef<ViewerHandle>(null);
  const [rawSelection, setRawSelection] = useState<string[]>([]);
  const selection = useMemo(() => rawSelection.filter((id) => index.has(id)), [rawSelection, index]);
  const [text, setText] = useState("");
  const [typed, setTyped] = useState<string[]>([]);
  const [tab, setTab] = useState<RightTab>("inspect");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [candidate, setCandidate] = useState<string | null>(null);
  const [pulse, setPulse] = useState<string[]>([]);
  const [scaleRequested, setScaleRequested] = useState(false);
  const [furniture, setFurniture] = useState<FurniturePlacement[] | null>(null);
  const [answerIds, setAnswerIds] = useState<string[]>([]);

  const pulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (pulseTimer.current) clearTimeout(pulseTimer.current);
  }, []);

  const refresh = useCallback(() => {
    void qc.invalidateQueries({ queryKey: keys.model(floorplanId) });
    void qc.invalidateQueries({ queryKey: keys.history(floorplanId) });
    void qc.invalidateQueries({ queryKey: keys.detail(floorplanId) });
  }, [floorplanId, keys, qc]);

  /** New HEAD: show it now, pulse what changed, then let the server's insights and history catch up. */
  const showApplied = useCallback(
    (res: CommandResponse) => {
      const { model: next, version: nextVersion } = res;
      if (next && nextVersion != null) qc.setQueryData<ModelEnvelope>(keys.model(floorplanId), (old) => (old ? { ...old, model: next, version: nextVersion } : old));
      refresh();
      onVersionChange(null);
      const ids = [...(res.changes?.added ?? []), ...(res.changes?.modified ?? [])];
      setPulse(ids);
      if (pulseTimer.current) clearTimeout(pulseTimer.current);
      pulseTimer.current = setTimeout(() => setPulse([]), PULSE_CLEAR_MS);
      if (res.summary) toast.success(res.summary);
    },
    [floorplanId, keys, onVersionChange, qc, refresh],
  );

  const flowApi = useCommandFlow({
    api,
    floorplanId,
    headVersion,
    onStale: refresh,
    onApplied: (res) => {
      setText("");
      showApplied(res);
    },
  });
  const { flow, discard, report } = flowApi;

  const undoRedo = useMutation({
    mutationFn: (dir: "undo" | "redo") => (dir === "undo" ? api.undo(floorplanId, headVersion) : api.redo(floorplanId, headVersion)),
    onSuccess: showApplied,
    onError: report,
  });
  const canUndo = !readOnly && !!history.data?.can_undo && !undoRedo.isPending && flow.state !== "busy";
  const canRedo = !readOnly && !!history.data?.can_redo && !undoRedo.isPending && flow.state !== "busy";
  const stepHistory = useCallback(
    (dir: "undo" | "redo") => {
      discard();
      undoRedo.mutate(dir);
    },
    [discard, undoRedo],
  );

  const keyState = useRef({ canUndo, canRedo, stepHistory, discard, active: false });
  useEffect(() => {
    keyState.current = { canUndo, canRedo, stepHistory, discard, active: flow.state !== "idle" };
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = keyState.current;
      if (e.key === "Escape" && k.active) {
        // Capture phase: a pending preview or question takes Esc before the viewer clears the selection.
        e.preventDefault();
        k.discard();
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z" && !isTyping(e.target)) {
        e.preventDefault();
        if (e.shiftKey) {
          if (k.canRedo) k.stepHistory("redo");
        } else if (k.canUndo) k.stepHistory("undo");
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);

  const send = useCallback(
    (source: CommandSource, persist = false) => {
      if ("instruction" in source) setTyped((t) => [source.instruction, ...t.filter((x) => x !== source.instruction)]);
      void (persist ? flowApi.apply(source) : flowApi.preview(source));
    },
    [flowApi],
  );
  const onCommand = useCallback((command: CommandInput) => send({ command }), [send]);

  const onPick = useCallback(
    (id: string) => {
      setRawSelection([id]);
      setTab("inspect");
      setSheetOpen(false);
      viewer.current?.zoomToElement(id);
    },
    [],
  );
  const onLink = useCallback((id: string) => {
    setRawSelection([id]);
    viewer.current?.zoomToElement(id);
  }, []);

  const onCandidateFocus = useCallback((c: Candidate | null) => {
    setCandidate(c?.id ?? null);
    if (c) viewer.current?.panToPoint({ x: c.x, y: c.y });
  }, []);

  const requestScale = useCallback(() => {
    discard();
    setTab("inspect");
    setSheetOpen(true);
    setScaleRequested(true);
  }, [discard]);
  const scaleConsumed = useCallback(() => setScaleRequested(false), []);

  const preview = flow.state === "preview" ? flow.response : null;
  const shownFurniture = tab === "analyze" ? furniture : null;
  const overlay = useMemo(() => {
    if (preview) return previewOverlay(preview.changes, head.data?.model, preview.model);
    if (!shownFurniture || !model) return undefined;
    // Proposed furniture is shown, never saved: nothing here reaches the model.
    const items: Furniture[] = shownFurniture.map((f) => ({ id: f.id, bbox: f.bbox, category: f.category, confidence: null, source: "INFERRED" }));
    return previewOverlay({ added: items.map((i) => i.id), modified: [], removed: [] }, model, { ...model, furniture: [...model.furniture, ...items] });
  }, [preview, head.data?.model, shownFurniture, model]);

  /** Layout and fix-it suggestions: same preview → Apply path as any edit, with the plan in view. */
  const previewSuggestion = useCallback(
    (command: CommandInput) => {
      setSheetOpen(false);
      onCommand(command);
    },
    [onCommand],
  );
  const showAnswer = useCallback((ids: string[]) => {
    setAnswerIds(ids);
    if (ids.length === 1) viewer.current?.zoomToElement(ids[0]);
  }, []);
  const highlightIds = candidate ? [candidate] : tab === "ask" && answerIds.length ? answerIds : undefined;

  const pastInstructions = useMemo(() => {
    const server = history.data?.edits.flatMap((e) => e.instruction ?? []) ?? [];
    return [...new Set([...typed, ...server])];
  }, [typed, history.data]);

  const preprocessed = artifacts.data?.find((a) => a.kind === "preprocessed")?.url ?? null;
  const fp = floorplan.data;

  const onAudio = useCallback(
    async (audio: Blob) => {
      const res = await api.postAudio(floorplanId, audio, { expectedVersion: headVersion, dryRun: true });
      if (!res.transcript) throw new Error("No transcript");
      return res.transcript;
    },
    [api, floorplanId, headVersion],
  );

  const backToProject = (
    <Button asChild size="sm" variant="outline">
      <Link href={`/projects/${projectId}`}>Back to project</Link>
    </Button>
  );

  const body = (() => {
    if (floorplan.isPending) return <CanvasSkeleton />;
    if (floorplan.isError) {
      const missing = floorplan.error instanceof ApiError && floorplan.error.status === 404;
      return (
        <Message
          icon={<FileQuestion className="size-5" strokeWidth={1.5} />}
          title={missing ? "This plan doesn't exist" : "The plan couldn't load"}
          action={
            <>
              {!missing && (
                <Button size="sm" onClick={() => floorplan.refetch()}>
                  <RotateCw strokeWidth={1.5} /> Retry
                </Button>
              )}
              {backToProject}
            </>
          }
        >
          {missing ? "It may have been deleted, or it belongs to another account." : floorplan.error.message}
        </Message>
      );
    }
    if (fp?.status === "FAILED" && !ready)
      return (
        <Message icon={<AlertTriangle className="size-5 text-danger" strokeWidth={1.5} />} title="Processing failed" action={backToProject}>
          {fp.latest_job?.error_message ?? "We couldn't read this drawing."} Upload a cleaner scan, or retry it from the project page.
        </Message>
      );
    if (!ready)
      return (
        <Message icon={<Loader2 className="size-5 animate-spin" strokeWidth={1.5} />} title="Reading the drawing" action={<Button asChild size="sm" variant="outline"><Link href={`/projects/${projectId}`}>See the timeline</Link></Button>}>
          The plan opens here as soon as processing finishes.
        </Message>
      );
    if (version !== null && pinned.isError)
      return (
        <Message icon={<FileQuestion className="size-5" strokeWidth={1.5} />} title={`Version ${version} isn't available`} action={<Button size="sm" onClick={() => onVersionChange(null)}>Back to HEAD</Button>} />
      );
    if (head.isError && !head.data)
      return (
        <Message icon={<AlertTriangle className="size-5 text-danger" strokeWidth={1.5} />} title="The model couldn't load" action={<Button size="sm" onClick={() => head.refetch()}><RotateCw strokeWidth={1.5} /> Retry</Button>}>
          {head.error.message}
        </Message>
      );
    if (!model || !envelope) return <CanvasSkeleton />;

    const counts = envelope.summary;
    const empty = !model.walls.length && !model.rooms.length && !counts.doors && !counts.windows;

    const canvas = (
      <FloorPlanViewer
        ref={viewer}
        model={model}
        selection={selection}
        onSelectionChange={(ids) => {
          setRawSelection(ids);
          if (ids.length) setTab("inspect");
        }}
        overlay={overlay}
        highlightIds={highlightIds}
        pulseIds={pulse}
        underlayUrl={preprocessed}
        readOnly={readOnly}
      >
        {readOnly && (
          <div className="absolute top-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-3 rounded-md border bg-popover px-3 py-1.5 text-ui shadow-md" data-testid="read-only-bar" role="status">
            <span>
              Viewing <span className="numeric">v{version}</span>, read-only
            </span>
            <Button size="xs" variant="outline" onClick={() => onVersionChange(null)}>
              Back to HEAD
            </Button>
          </div>
        )}
        {empty && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-6" data-testid="empty-plan">
            <p className="max-w-xs text-center text-ui text-muted-foreground">Nothing was detected in this drawing. Try a cleaner scan with darker walls, or add walls by typing below.</p>
          </div>
        )}
        <CommandBar
          flow={flow}
          text={text}
          onTextChange={setText}
          disabled={readOnly}
          history={pastInstructions}
          hasScale={!!model.coordinate_system.mm_per_pixel}
          onPreview={(instruction) => send({ instruction })}
          onApplyInstruction={(instruction) => send({ instruction }, true)}
          onApply={() => void flowApi.apply()}
          onDiscard={discard}
          onPick={flowApi.pick}
          onCandidateFocus={onCandidateFocus}
          onSetScale={requestScale}
          onAudio={onAudio}
          onVoiceError={report}
        />
      </FloorPlanViewer>
    );

    const tabs = (
      <Tabs value={tab} onValueChange={(v) => setTab(v as RightTab)} className="flex h-full min-h-0 flex-col gap-0">
        <TabsList variant="line" className={cn("h-9 w-full shrink-0 justify-start overflow-x-auto rounded-none border-b px-2 [scrollbar-width:none]", !wide && "pr-10")}>
          {!wide && <TabsTrigger value="outline" className="text-ui">Outline</TabsTrigger>}
          <TabsTrigger value="inspect" className="flex-none px-2 text-ui">Inspect</TabsTrigger>
          <TabsTrigger value="insights" className="flex-none px-2 text-ui">Insights</TabsTrigger>
          <TabsTrigger value="analyze" className="flex-none px-2 text-ui">Analyze</TabsTrigger>
          <TabsTrigger value="ask" className="flex-none px-2 text-ui">Ask</TabsTrigger>
          <TabsTrigger value="history" className="flex-none px-2 text-ui">History</TabsTrigger>
        </TabsList>
        <ScrollArea className="min-h-0 flex-1">
          {!wide && (
            <TabsContent value="outline" className="h-[70dvh]">
              <Outline model={model} selection={selection} onPick={onPick} />
            </TabsContent>
          )}
          <TabsContent value="inspect">
            <Inspector model={model} selection={selection} readOnly={readOnly} scaleRequested={scaleRequested} onScaleConsumed={scaleConsumed} onPick={onLink} onCommand={onCommand} />
          </TabsContent>
          <TabsContent value="insights">
            <InsightsPanel insights={envelope.insights} onCalibrate={requestScale} readOnly={readOnly} />
          </TabsContent>
          {/* Kept mounted: picking an element or switching tabs must not lose the open report or the conversation. */}
          <TabsContent value="analyze" forceMount className="data-[state=inactive]:hidden">
            <AnalyzePanel active={tab === "analyze"} floorplanId={floorplanId} version={envelope.version} readOnly={readOnly} onCalibrate={requestScale} onPick={wide ? onLink : onPick} onPreview={previewSuggestion} onFurniture={setFurniture} />
          </TabsContent>
          <TabsContent value="ask" forceMount className="data-[state=inactive]:hidden">
            <AskPanel floorplanId={floorplanId} version={envelope.version} onAnswer={showAnswer} />
          </TabsContent>
          <TabsContent value="history">
            <HistoryPanel history={history.data} loading={history.isPending} viewing={version} onView={onVersionChange} />
          </TabsContent>
        </ScrollArea>
      </Tabs>
    );

    if (!wide)
      return (
        <div className="relative h-full">
          {canvas}
          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <SheetTrigger asChild>
              <Button size="sm" variant="outline" className="absolute top-3 right-3 z-10 bg-card">
                <PanelRight strokeWidth={1.5} /> Details
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-(--inspector-w) gap-0 p-0 sm:max-w-sm">
              <SheetTitle className="sr-only">Plan details</SheetTitle>
              {tabs}
            </SheetContent>
          </Sheet>
        </div>
      );

    return (
      <ResizablePanelGroup orientation="horizontal" id="workspace-panels">
        <ResizablePanel id="outline" defaultSize={240} minSize={180} maxSize={420}>
          <div className="h-full bg-card">
            <Outline model={model} selection={selection} onPick={onPick} />
          </div>
        </ResizablePanel>
        <ResizableHandle aria-label="Resize outline" />
        <ResizablePanel id="canvas" minSize={320}>
          {canvas}
        </ResizablePanel>
        <ResizableHandle aria-label="Resize inspector" />
        <ResizablePanel id="inspector" defaultSize={350} minSize={240} maxSize={460}>
          <div className="h-full bg-card">{tabs}</div>
        </ResizablePanel>
      </ResizablePanelGroup>
    );
  })();

  return (
    <div className="flex h-[calc(100dvh-var(--topbar-h))] min-h-0 flex-col" data-testid="workspace">
      <header className="flex h-(--topbar-h) shrink-0 items-center gap-2 border-b bg-card px-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button asChild variant="ghost" size="icon-sm" aria-label="Back to project">
              <Link href={`/projects/${projectId}`}>
                <ArrowLeft strokeWidth={1.5} />
              </Link>
            </Button>
          </TooltipTrigger>
          <TooltipContent>Back to project</TooltipContent>
        </Tooltip>
        <h1 className="max-w-[28ch] truncate text-ui font-medium" title={fp?.original_filename}>
          {fp?.original_filename ?? "Floor plan"}
        </h1>
        {envelope && (
          <Badge variant="outline" className="numeric font-normal" data-testid="version-chip">
            v{envelope.version}
            {!readOnly && " · HEAD"}
          </Badge>
        )}
        {fp && <StatusBadge status={fp.status} />}
        <div className="ml-auto flex items-center gap-1">
          <IconAction label="Undo" kbd={`${MOD}Z`} disabled={!canUndo} onClick={() => stepHistory("undo")}>
            <Undo2 strokeWidth={1.5} />
          </IconAction>
          <IconAction label="Redo" kbd={`${MOD}⇧Z`} disabled={!canRedo} onClick={() => stepHistory("redo")}>
            <Redo2 strokeWidth={1.5} />
          </IconAction>
          <IconAction
            label="History"
            active={tab === "history" && (wide || sheetOpen)}
            onClick={() => {
              const open = tab === "history" && (wide || sheetOpen);
              setTab(open ? "inspect" : "history");
              if (!wide) setSheetOpen(!open);
            }}
          >
            <HistoryIcon strokeWidth={1.5} />
          </IconAction>
          <Downloads floorplan={fp} artifacts={artifacts.data} />
        </div>
      </header>
      {fp && fp.warnings.length > 0 && ready && (
        <p className="flex shrink-0 items-center gap-2 border-b bg-card px-3 py-1 text-micro text-warning" data-testid="warnings">
          <ScanSearch className="size-3.5" strokeWidth={1.5} aria-hidden /> {fp.warnings.join(" ")}
        </p>
      )}
      <div className="min-h-0 flex-1">{body}</div>
    </div>
  );
}

const ARTIFACT_LABEL: Record<Artifact["kind"], string> = {
  preprocessed: "Preprocessed image",
  walls_overlay: "Walls overlay",
  detected_elements: "Detected elements",
  semantic_model: "Building model (JSON)",
};

function Downloads({ floorplan, artifacts }: { floorplan: FloorPlan | undefined; artifacts: Artifact[] | undefined }) {
  const hasAny = !!floorplan?.download_url || !!artifacts?.length;
  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label="Downloads" disabled={!hasAny}>
              <Download strokeWidth={1.5} />
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent>Downloads</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end" className="w-56">
        {floorplan?.download_url && (
          <DropdownMenuItem asChild>
            <a href={floorplan.download_url} target="_blank" rel="noopener noreferrer">
              Original upload
            </a>
          </DropdownMenuItem>
        )}
        {artifacts?.map((a) => (
          <DropdownMenuItem key={a.id} asChild>
            <a href={a.url} target="_blank" rel="noopener noreferrer">
              {ARTIFACT_LABEL[a.kind]}
            </a>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
