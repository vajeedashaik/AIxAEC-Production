"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, Loader2, RotateCw, XCircle } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import type { CommandInput, ComplianceCheck, ComplianceReport, CostEstimate, CostRates, CostRatesInput, FurniturePlacement, InteriorPlan, LayoutSuggestions, StructuralReport, Takeoff } from "@/contracts";
import { queryKeys, useApi } from "@/lib/api";
import { cn } from "@/lib/utils";

import { downloadCsv } from "./csv";

const VIEWS = { takeoff: "Quantities and BOQ", cost: "Cost estimate", compliance: "Code compliance", interior: "Interior design", layouts: "Layout suggestions", structure: "Structural suggestions" } as const;
type View = keyof typeof VIEWS;

const RATES_KEY = "aec.cost-rates";
const qty = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });
const heading = "pb-1 text-micro text-muted-foreground";

function loadRates(): CostRatesInput | null {
  try {
    return JSON.parse(localStorage.getItem(RATES_KEY) ?? "null") as CostRatesInput | null;
  } catch {
    return null;
  }
}

function saveRates(rates: CostRatesInput | null) {
  try {
    if (rates) localStorage.setItem(RATES_KEY, JSON.stringify(rates));
    else localStorage.removeItem(RATES_KEY);
  } catch {
    // Private windows can refuse storage; the rates still apply for this session.
  }
}

function ExportButton({ onClick }: { onClick(): void }) {
  return (
    <Button size="xs" variant="outline" onClick={onClick}>
      <Download strokeWidth={1.5} /> CSV
    </Button>
  );
}

function Assumptions({ items }: { items: { label: string; value: string }[] }) {
  return (
    <details className="text-micro text-muted-foreground">
      <summary className="cursor-pointer">Assumptions</summary>
      <dl className="mt-1 flex flex-col gap-1">
        {items.map((a) => (
          <div key={a.label}>
            <dt className="inline font-medium">{a.label}: </dt>
            <dd className="inline">{a.value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

/* ── Takeoff ──────────────────────────────────────────────────────────────── */

export function TakeoffView({ takeoff }: { takeoff: Takeoff }) {
  const groups = useMemo(() => Map.groupBy(takeoff.items, (i) => i.category), [takeoff]);
  const exportBoq = () => downloadCsv("bill-of-quantities.csv", [["Code", "Category", "Description", "Unit", "Quantity", "Basis"], ...takeoff.items.map((i) => [i.code, i.category, i.description, i.unit, i.quantity, i.basis])]);
  return (
    <div className="flex flex-col gap-4" data-testid="takeoff">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-medium">Bill of Quantities</h2>
        <ExportButton onClick={exportBoq} />
      </div>
      {[...groups].map(([category, items]) => (
        <section key={category}>
          <h3 className={heading}>{category}</h3>
          <dl className="flex flex-col gap-1">
            {items.map((i) => (
              <div key={i.code} className="flex items-baseline justify-between gap-3" title={i.basis}>
                <dt className="text-muted-foreground">{i.description}</dt>
                <dd className="numeric text-right">
                  {qty(i.quantity)} {i.unit}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
      <Assumptions items={takeoff.assumptions} />
    </div>
  );
}

/* ── Cost ─────────────────────────────────────────────────────────────────── */

const rateLabel = (key: string) => {
  const text = key.replace(/_per_/, " per ").replace(/_each$/, " each").replace(/_percent$/, " %").replace(/_/g, " ");
  return text[0].toUpperCase() + text.slice(1);
};

export function CostView({ estimate, onRates, busy }: { estimate: CostEstimate; onRates(rates: CostRatesInput | null): void; busy: boolean }) {
  const [draft, setDraft] = useState<CostRates>(estimate.rates);
  const money = (n: number) => `${estimate.currency} ${n.toLocaleString(estimate.currency === "INR" ? "en-IN" : undefined, { maximumFractionDigits: 0 })}`;
  const totals: [string, number][] = [
    ["Material", estimate.material_cost],
    ["Painting", estimate.painting_cost],
    ["Flooring", estimate.flooring_cost],
    ["Electrical", estimate.electrical_cost],
    ["Plumbing", estimate.plumbing_cost],
    ["Labour", estimate.labour_cost],
    ["Contingency", estimate.contingency],
  ];
  const valid = Object.entries(draft).every(([k, v]) => (k === "currency" ? String(v).trim() : Number.isFinite(v) && (v as number) >= 0));
  const exportCost = () => downloadCsv("cost-estimate.csv", [["Category", "Description", "Quantity", "Unit", `Rate (${estimate.currency})`, `Amount (${estimate.currency})`], ...estimate.lines.map((l) => [l.category, l.description, l.quantity, l.unit, l.rate, l.amount]), ["Total", "Construction cost", "", "", "", estimate.construction_cost]]);
  return (
    <div className="flex flex-col gap-4" data-testid="cost">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-micro text-muted-foreground">Construction cost</p>
          <p className="numeric text-2xl font-semibold tracking-tight" data-testid="construction-cost">
            {money(estimate.construction_cost)}
          </p>
          <p className="numeric text-micro text-muted-foreground">{money(estimate.cost_per_m2)} per m² · {qty(estimate.tile_count)} tiles</p>
        </div>
        <ExportButton onClick={exportCost} />
      </div>
      <dl className="flex flex-col gap-1">
        {totals.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-3">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="numeric">{money(value)}</dd>
          </div>
        ))}
      </dl>
      <p className="flex items-start gap-2 rounded-md border p-2 text-micro text-warning">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.5} aria-hidden /> Default rates are rough India averages. Enter local prices for a usable estimate.
      </p>
      <details>
        <summary className="cursor-pointer text-micro text-muted-foreground">Edit rates</summary>
        <form
          className="mt-2 flex flex-col gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid) onRates(draft);
          }}
        >
          {Object.entries(draft).map(([key, value]) => (
            <div key={key} className="grid grid-cols-[1fr_6rem] items-center gap-2">
              <Label htmlFor={`rate-${key}`} className="text-micro font-normal text-muted-foreground">
                {rateLabel(key)}
              </Label>
              <Input
                id={`rate-${key}`}
                className="numeric h-7 text-ui"
                value={Number.isNaN(value) ? "" : value}
                {...(key === "currency" ? { maxLength: 8 } : { type: "number", min: 0, step: "any" })}
                onChange={(e) => setDraft((d) => ({ ...d, [key]: key === "currency" ? e.target.value : e.target.valueAsNumber }))}
              />
            </div>
          ))}
          <div className="flex gap-2 pt-1">
            <Button size="sm" type="submit" disabled={!valid || busy}>
              Apply rates
            </Button>
            <Button size="sm" type="button" variant="ghost" onClick={() => onRates(null)}>
              Reset
            </Button>
          </div>
        </form>
      </details>
      <Assumptions items={estimate.assumptions} />
    </div>
  );
}

/* ── Compliance ───────────────────────────────────────────────────────────── */

const STATUS: Record<ComplianceCheck["status"], { icon: typeof XCircle; tone: string; label: string; rank: number }> = {
  FAIL: { icon: XCircle, tone: "text-danger", label: "Fail", rank: 0 },
  WARN: { icon: AlertTriangle, tone: "text-warning", label: "Warning", rank: 1 },
  PASS: { icon: CheckCircle2, tone: "text-success", label: "Pass", rank: 2 },
};

export function ComplianceView({ report, onPick }: { report: ComplianceReport; onPick(id: string): void }) {
  const [showPassed, setShowPassed] = useState(false);
  const ordered = useMemo(() => [...report.checks].sort((a, b) => STATUS[a.status].rank - STATUS[b.status].rank), [report]);
  const shown = showPassed ? ordered : ordered.filter((c) => c.status !== "PASS");
  const exportReport = () => downloadCsv("compliance-report.csv", [["Status", "Category", "Rule", "Subject", "Measured", "Required"], ...ordered.map((c) => [c.status, c.category, c.rule, c.subject, c.measured, c.required])]);
  return (
    <div className="flex flex-col gap-4" data-testid="compliance">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-medium">{report.profile}</h2>
        <ExportButton onClick={exportReport} />
      </div>
      <p className="numeric flex gap-3" data-testid="compliance-summary">
        <span className="text-danger">{report.failed} failed</span>
        <span className="text-warning">{report.warnings} warnings</span>
        <span className="text-success">{report.passed} passed</span>
      </p>
      <p className="text-micro text-muted-foreground">{report.disclaimer}</p>
      <ul className="flex flex-col gap-1">
        {shown.map((c, i) => {
          const { icon: Icon, tone, label } = STATUS[c.status];
          const id = c.element_id;
          const body = (
            <>
              <Icon className={cn("mt-0.5 size-3.5 shrink-0", tone)} strokeWidth={1.5} aria-label={label} />
              <span className="min-w-0">
                <span className="block">
                  {c.subject}: {c.rule.toLowerCase()}
                </span>
                <span className="numeric block text-micro text-muted-foreground">
                  {c.measured}, required {c.required}
                </span>
              </span>
            </>
          );
          return (
            <li key={`${c.rule}-${c.subject}-${i}`}>
              {id ? (
                <button type="button" className="flex w-full items-start gap-2 rounded-md p-1 text-left hover:bg-muted" onClick={() => onPick(id)}>
                  {body}
                </button>
              ) : (
                <div className="flex items-start gap-2 p-1">{body}</div>
              )}
            </li>
          );
        })}
        {!shown.length && <li className="text-muted-foreground">Nothing failed or needs attention.</li>}
      </ul>
      <Button size="xs" variant="ghost" className="self-start" onClick={() => setShowPassed((s) => !s)}>
        {showPassed ? "Hide passed checks" : `Show ${report.passed} passed checks`}
      </Button>
    </div>
  );
}

/* ── Interior ─────────────────────────────────────────────────────────────── */

export function InteriorView({ plan, onFurniture }: { plan: InteriorPlan; onFurniture(items: FurniturePlacement[] | null): void }) {
  const [show, setShow] = useState(false);
  const [theme, setTheme] = useState(plan.themes[0].name);
  const active = plan.themes.find((t) => t.name === theme) ?? plan.themes[0];
  useEffect(() => () => onFurniture(null), [onFurniture]); // never leave ghosts behind when this view goes away
  return (
    <div className="flex flex-col gap-4" data-testid="interior">
      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <Label htmlFor="show-furniture" className="font-normal">
            Show {plan.furniture.length} furniture pieces on the plan
          </Label>
          <Switch
            id="show-furniture"
            checked={show}
            onCheckedChange={(on) => {
              setShow(on);
              onFurniture(on ? plan.furniture : null);
            }}
          />
        </div>
        <p className="text-micro text-muted-foreground">A proposal drawn over the plan. It isn&apos;t saved to the model.</p>
        {plan.notes.map((n) => (
          <p key={n} className="text-micro text-warning">
            {n}
          </p>
        ))}
      </section>
      <section className="flex flex-col gap-2">
        <h3 className={heading}>Theme</h3>
        <Select value={theme} onValueChange={(v) => setTheme(v as typeof theme)}>
          <SelectTrigger className="h-8 w-full text-ui" aria-label="Interior theme">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {plan.themes.map((t) => (
              <SelectItem key={t.name} value={t.name}>
                {t.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p>{active.summary}</p>
        <ul className="flex gap-2">
          {active.palette.map((s) => (
            <li key={s.hex} className="flex flex-1 flex-col gap-1">
              <span className="h-8 rounded-sm border" style={{ background: s.hex }} aria-hidden />
              <span className="text-micro text-muted-foreground">{s.name}</span>
            </li>
          ))}
        </ul>
        <p className="text-micro text-muted-foreground">
          {active.materials.join(" · ")}. {active.lighting}.
        </p>
        <dl className="flex flex-col gap-1">
          {active.room_finishes.map((f) => (
            <div key={f.room}>
              <dt className="inline text-muted-foreground">{f.room}: </dt>
              <dd className="inline">{f.finish}</dd>
            </div>
          ))}
        </dl>
      </section>
      <section>
        <h3 className={heading}>Lighting</h3>
        <ul className="flex flex-col gap-2">
          {plan.lighting.map((l) => (
            <li key={l.room_id}>
              <p className="flex justify-between gap-2">
                <span>{l.room}</span>
                <span className="numeric text-muted-foreground">
                  {l.fixtures} × {l.colour_temperature_k} K
                </span>
              </p>
              <p className="text-micro text-muted-foreground">
                {l.fixture}. <span className="numeric">{qty(l.lumens)} lm</span> for <span className="numeric">{l.target_lux} lux</span>. {l.daylight}.
              </p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/* ── Layouts ──────────────────────────────────────────────────────────────── */

const GOALS = ["Can this house have another bedroom?", "Increase parking.", "Make kitchen larger."];

export function LayoutsView({ floorplanId, readOnly, onPreview }: { floorplanId: string; readOnly: boolean; onPreview(c: CommandInput): void }) {
  const api = useApi();
  const [goal, setGoal] = useState("");
  const suggest = useMutation<LayoutSuggestions, Error, string>({ mutationFn: (text) => api.suggestLayouts(floorplanId, text) });
  const submit = (text: string) => {
    if (text.trim()) suggest.mutate(text.trim());
  };
  return (
    <div className="flex flex-col gap-3" data-testid="layouts">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit(goal);
        }}
      >
        <Input aria-label="Layout goal" placeholder="What should change?" className="h-8 text-ui" maxLength={300} value={goal} onChange={(e) => setGoal(e.target.value)} />
        <Button size="sm" type="submit" disabled={suggest.isPending || readOnly || !goal.trim()}>
          Suggest
        </Button>
      </form>
      <div className="flex flex-wrap gap-1">
        {GOALS.map((g) => (
          <Button
            key={g}
            size="xs"
            variant="outline"
            disabled={suggest.isPending || readOnly}
            onClick={() => {
              setGoal(g);
              submit(g);
            }}
          >
            {g}
          </Button>
        ))}
      </div>
      {readOnly && <p className="text-micro text-muted-foreground">Go back to HEAD to get suggestions.</p>}
      {suggest.isPending && (
        <p className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" strokeWidth={1.5} aria-hidden /> Testing layouts against the plan
        </p>
      )}
      {suggest.isError && <p className="text-danger">{suggest.error.message}</p>}
      {suggest.data && (
        <div className="flex flex-col gap-2" role="status">
          <p>{suggest.data.answer}</p>
          {suggest.data.options.map((o, i) => (
            <article key={o.title} className="flex flex-col gap-1.5 rounded-md border p-2" data-testid="layout-option">
              <h3 className="font-medium">
                <span className="numeric text-muted-foreground">{i + 1}. </span>
                {o.title}
              </h3>
              <p className="text-micro text-muted-foreground">{o.rationale}</p>
              {o.target_area_before_m2 != null && o.target_area_after_m2 != null && (
                <p className="numeric text-micro">
                  {o.target_area_before_m2} m² → {o.target_area_after_m2} m²
                </p>
              )}
              <div className="flex items-center gap-2">
                <Button size="xs" variant="outline" disabled={readOnly} onClick={() => onPreview(o.command)}>
                  Preview on plan
                </Button>
                {o.new_compliance_failures > 0 && (
                  <Badge variant="outline" className="font-normal text-warning">
                    +{o.new_compliance_failures} failures
                  </Badge>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Structure ────────────────────────────────────────────────────────────── */

export function StructureView({ report, readOnly, onPick, onPreview }: { report: StructuralReport; readOnly: boolean; onPick(id: string): void; onPreview(c: CommandInput): void }) {
  const groups = useMemo(() => Map.groupBy(report.suggestions, (s) => s.category), [report]);
  return (
    <div className="flex flex-col gap-4" data-testid="structure">
      <p className="text-micro text-muted-foreground">{report.disclaimer}</p>
      {[...groups].map(([category, items]) => (
        <section key={category} className="flex flex-col gap-2">
          <h3 className={heading}>{category}</h3>
          {items.map((s, i) => {
            const id = s.element_id;
            const command = s.command;
            return (
              <article key={`${s.title}-${i}`} className="flex flex-col items-start gap-1">
                {id ? (
                  <button type="button" className="text-left font-medium underline-offset-2 hover:underline" onClick={() => onPick(id)}>
                    {s.title}
                  </button>
                ) : (
                  <h4 className="font-medium">{s.title}</h4>
                )}
                <p className="text-micro text-muted-foreground">{s.detail}</p>
                {command && (
                  <Button size="xs" variant="outline" disabled={readOnly} onClick={() => onPreview(command)}>
                    Preview fix
                  </Button>
                )}
              </article>
            );
          })}
        </section>
      ))}
      {!report.suggestions.length && <p className="text-muted-foreground">No suggestions for this plan.</p>}
    </div>
  );
}

/* ── Panel ────────────────────────────────────────────────────────────────── */

interface AnalyzePanelProps {
  active: boolean;
  floorplanId: string;
  version: number;
  readOnly: boolean;
  onCalibrate(): void;
  onPick(id: string): void;
  onPreview(command: CommandInput): void;
  onFurniture(items: FurniturePlacement[] | null): void;
}

export function AnalyzePanel({ active, floorplanId, version, readOnly, onCalibrate, onPick, onPreview, onFurniture }: AnalyzePanelProps) {
  const api = useApi();
  const [view, setView] = useState<View>("takeoff");
  const [rates, setRates] = useState<CostRatesInput | null>(loadRates);
  const analysis = useQuery({
    queryKey: queryKeys.floorplans.analysis(floorplanId, version, rates),
    queryFn: () => api.analyze(floorplanId, version, rates),
    enabled: active && view !== "layouts",
    staleTime: Infinity, // a version and rates fully determine the result
  });
  const updateRates = (next: CostRatesInput | null) => {
    saveRates(next);
    setRates(next);
  };

  let content: ReactNode;
  if (view === "layouts") content = <LayoutsView floorplanId={floorplanId} readOnly={readOnly} onPreview={onPreview} />;
  else if (analysis.isPending)
    content = (
      <div className="flex flex-col gap-2" data-testid="analysis-loading">
        <Skeleton className="h-5" />
        <Skeleton className="h-5" />
        <Skeleton className="h-5" />
      </div>
    );
  else if (analysis.isError)
    content = (
      <div className="flex flex-col items-start gap-2">
        <p className="text-danger">{analysis.error.message}</p>
        <Button size="sm" variant="outline" onClick={() => analysis.refetch()}>
          <RotateCw strokeWidth={1.5} /> Retry
        </Button>
        {rates && (
          <Button size="sm" variant="ghost" onClick={() => updateRates(null)}>
            Reset saved rates
          </Button>
        )}
      </div>
    );
  else if (analysis.data.needs_scale)
    content = (
      <div className="flex flex-col items-start gap-2 rounded-md border p-3" data-testid="analysis-needs-scale">
        <p className="text-muted-foreground">Quantities, cost and code checks need real measurements. Calibrate the plan first.</p>
        {!readOnly && (
          <Button size="sm" variant="outline" onClick={onCalibrate}>
            Set scale
          </Button>
        )}
      </div>
    );
  else {
    const a = analysis.data;
    content = (
      <>
        {view === "takeoff" && a.takeoff && <TakeoffView takeoff={a.takeoff} />}
        {view === "cost" && a.estimate && <CostView key={JSON.stringify(a.estimate.rates)} estimate={a.estimate} onRates={updateRates} busy={analysis.isFetching} />}
        {view === "compliance" && a.compliance && <ComplianceView report={a.compliance} onPick={onPick} />}
        {view === "interior" && a.interior && <InteriorView plan={a.interior} onFurniture={onFurniture} />}
        {view === "structure" && a.structural && <StructureView report={a.structural} readOnly={readOnly} onPick={onPick} onPreview={onPreview} />}
      </>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4 text-ui" data-testid="analyze">
      <Select value={view} onValueChange={(v) => setView(v as View)}>
        <SelectTrigger className="h-8 w-full text-ui" aria-label="Analysis">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(Object.keys(VIEWS) as View[]).map((v) => (
            <SelectItem key={v} value={v}>
              {VIEWS[v]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {content}
    </div>
  );
}
