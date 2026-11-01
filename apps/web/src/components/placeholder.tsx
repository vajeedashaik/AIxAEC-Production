import type { ReactNode } from "react";

/** P0 route placeholder. P5 replaces these pages; P6 replaces the workspace and playground. */
export function Placeholder({ title, owner, children }: { title: string; owner: string; children?: ReactNode }) {
  return (
    <section className="mx-auto flex w-full max-w-3xl flex-col gap-3 px-6 py-16">
      <p className="numeric text-micro uppercase tracking-wider text-muted-foreground">{owner} · placeholder</p>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {children && <div className="text-muted-foreground">{children}</div>}
    </section>
  );
}
