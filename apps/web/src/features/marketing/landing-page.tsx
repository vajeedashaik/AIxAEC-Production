import { CheckIcon, MicIcon, UploadIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

import { CapabilityList } from "./capability-list";
import { HeroDemo } from "./hero-demo";

const STAGE_LIST = ["Clean up image", "Find walls", "Read text", "Find openings", "Find rooms", "Calibrate scale", "Assemble model", "Save artifacts"];

function Hero() {
  return (
    <section className="grid lg:min-h-dvh lg:grid-cols-2">
      <div className="flex flex-col justify-between gap-12 bg-surface-sunken p-5 sm:p-10">
        <Link href="/" aria-label="AEC Studio home" className="w-fit">
          <Logo className="text-base" />
        </Link>
        <div>
          <h1 className="text-[clamp(2.25rem,3.9vw,3.75rem)] leading-[1.06] font-semibold tracking-tight">
            <span className="block overflow-hidden pb-[0.06em]">
              <span className="rise-line">Floor plans you edit</span>
            </span>
            <span className="block overflow-hidden pb-[0.06em]">
              <span className="rise-line" style={{ animationDelay: "110ms" }}>
                by saying what changes.
              </span>
            </span>
          </h1>
          <p className="fade-up mt-4 max-w-[46ch] text-base text-muted-foreground sm:text-lg" style={{ animationDelay: "500ms" }}>
            Upload a drawing and get a typed building model. Type or speak an edit, preview it, and keep every version.
          </p>
          <div className="fade-up mt-6 flex items-center gap-4" style={{ animationDelay: "500ms" }}>
            <Button asChild size="lg">
              <Link href="/sign-up">Upload a floor plan</Link>
            </Button>
            <Link href="/sign-in" className="text-sm underline-offset-4 hover:underline">
              Sign in
            </Link>
          </div>
        </div>
      </div>
      <div className="flex items-center justify-center bg-(--canvas-paper) p-5 sm:p-10">
        <HeroDemo />
      </div>
    </section>
  );
}

const StoryCard = ({ children }: { children: ReactNode }) => (
  <div data-ui className="w-full max-w-72 rounded-lg border bg-card p-3 text-ui text-card-foreground">
    {children}
  </div>
);

function Story() {
  const fields = [
    {
      className: "bg-surface-sunken",
      clause: "First, upload the drawing you already have.",
      card: (
        <StoryCard>
          <div className="flex items-center gap-2">
            <UploadIcon className="size-4 text-muted-foreground" strokeWidth={1.5} aria-hidden />
            <span className="min-w-0 flex-1 truncate font-medium">apartment.png</span>
            <span className="numeric text-micro text-muted-foreground">47.1 KB</span>
          </div>
          <Progress value={62} aria-label="Example upload progress" className="mt-2 h-1" />
          <p className="numeric mt-2 text-micro text-muted-foreground">62% · PNG, JPG or PDF</p>
        </StoryCard>
      ),
    },
    {
      className: "bg-accent",
      clause: "Then it reads the plan, in eight stages you can watch.",
      card: (
        <StoryCard>
          <ul className="flex flex-col gap-1">
            {STAGE_LIST.map((stage, i) => (
              <li key={stage} className={i > 4 ? "flex items-center gap-1.5 text-muted-foreground" : "flex items-center gap-1.5"}>
                {i <= 4 ? <CheckIcon className="size-3.5 text-success" strokeWidth={2} aria-hidden /> : <span aria-hidden className="size-3.5" />}
                {stage}
              </li>
            ))}
          </ul>
        </StoryCard>
      ),
    },
    {
      className: "bg-foreground text-background",
      clause: "Now edit it by typing or by voice.",
      card: (
        <StoryCard>
          <p className="flex items-center gap-1.5 text-muted-foreground">
            <MicIcon className="size-3.5" strokeWidth={1.5} aria-hidden />
            Heard
          </p>
          <p className="mt-1 text-sm">“rename the study to office”</p>
          <p className="mt-2 flex items-center gap-1.5 border-t pt-2">
            <CheckIcon className="size-3.5 text-success" strokeWidth={2} aria-hidden />
            Applied as <span className="numeric">v2</span>
          </p>
        </StoryCard>
      ),
    },
  ];
  return (
    <section aria-labelledby="how" className="grid md:grid-cols-3">
      {fields.map((f, i) => (
        <div key={f.clause} className={`flex min-h-[32rem] flex-col justify-between gap-10 p-5 sm:p-8 ${f.className}`}>
          <div className="min-h-[1.5em]">
            {i === 0 && (
              <h2 id="how" className="text-[clamp(1.5rem,2vw,2rem)] font-semibold tracking-tight">
                How it works
              </h2>
            )}
          </div>
          <div className="flex justify-center">{f.card}</div>
          <p className="max-w-[22ch] text-[clamp(1.5rem,2vw,2rem)] leading-tight font-medium tracking-tight">{f.clause}</p>
        </div>
      ))}
    </section>
  );
}

function Capabilities() {
  return (
    <section aria-label="Capabilities" className="mx-auto w-full max-w-7xl px-5 py-20 sm:px-10 lg:py-28">
      <CapabilityList />
    </section>
  );
}

function Pipeline() {
  const rows = [
    { step: "Parse", who: "Language model", note: "Reads your words. Its output is treated as untrusted.", tone: "text-muted-foreground" },
    { step: "Check schema", who: "Validator", note: "Only one of ten known operations gets through." },
    { step: "Resolve", who: "Entity resolver", note: "Finds the exact wall. If two match, it asks you." },
    { step: "Move geometry", who: "Geometry engine", note: "Deterministic. The same command gives the same plan." },
    { step: "Check constraints", who: "Geometry engine", note: "A plan that would break is rejected, and nothing changes." },
    { step: "Save version", who: "Version store", note: "A new immutable version. The old one stays." },
  ];
  return (
    <section aria-labelledby="trust" className="bg-foreground text-background">
      <div className="mx-auto grid w-full max-w-7xl gap-12 px-5 py-20 sm:px-10 lg:grid-cols-[5fr_7fr] lg:py-28">
        <div>
          <h2 id="trust" className="text-[clamp(2rem,3.6vw,3.25rem)] leading-[1.08] font-semibold tracking-tight">
            The AI never moves a wall. The geometry engine does.
          </h2>
          <p className="mt-5 max-w-[42ch] text-lg opacity-75">The model only turns your sentence into a command. It never touches the drawing, and it can&apos;t guess its way past a check.</p>
        </div>
        <ol data-ui className="overflow-hidden rounded-lg border bg-card text-card-foreground">
          {rows.map((r, i) => (
            <li key={r.step} className="grid grid-cols-[1.5rem_1fr] gap-x-3 border-b px-4 py-3 last:border-b-0 sm:grid-cols-[1.5rem_11rem_1fr]">
              <span aria-hidden className="numeric text-ui text-muted-foreground">
                {i + 1}
              </span>
              <span>
                <span className="block text-sm font-medium">{r.step}</span>
                <span className="block text-ui text-muted-foreground">{r.who}</span>
              </span>
              <span className="col-start-2 text-sm text-muted-foreground sm:col-start-3">{r.note}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Cta() {
  return (
    <section className="mx-auto flex w-full max-w-7xl flex-wrap items-end justify-between gap-8 px-5 py-20 sm:px-10 lg:py-28">
      <h2 className="max-w-[18ch] text-[clamp(2rem,3.6vw,3.25rem)] leading-[1.08] font-semibold tracking-tight">Bring one drawing. See what it understands.</h2>
      <Button asChild size="lg">
        <Link href="/sign-up">Upload a floor plan</Link>
      </Button>
    </section>
  );
}

function Footer() {
  return (
    <footer className="grid gap-2 p-2 sm:grid-cols-3">
      <div className="flex min-h-44 flex-col justify-between gap-6 rounded-lg bg-surface-sunken p-5 sm:col-span-2">
        <Logo className="text-lg" />
        <p className="max-w-[44ch] text-sm text-muted-foreground">A precision tool for people who work from floor plans.</p>
      </div>
      <nav aria-label="Footer" className="flex min-h-44 flex-col gap-2 rounded-lg bg-surface-sunken p-5 text-base">
        <Link href="/sign-up" className="w-fit underline-offset-4 hover:underline">
          Create an account
        </Link>
        <Link href="/sign-in" className="w-fit underline-offset-4 hover:underline">
          Sign in
        </Link>
      </nav>
    </footer>
  );
}

export function LandingPage() {
  return (
    <>
      <main>
        <Hero />
        <Story />
        <Capabilities />
        <Pipeline />
        <Cta />
      </main>
      <Footer />
    </>
  );
}
