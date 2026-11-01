import Link from "next/link";

import { Logo } from "@/components/logo";
import { PlanDrawing } from "@/features/marketing/plan-drawing";
import { INITIAL_PLAN } from "@/features/marketing/plan-geometry";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <aside className="hidden flex-col justify-between gap-8 overflow-hidden bg-(--canvas-paper) p-10 lg:flex">
        <Link href="/" aria-label="AEC Studio home" className="w-fit">
          <Logo className="text-base" />
        </Link>
        <PlanDrawing plan={INITIAL_PLAN} className="mx-auto w-full max-w-xl" />
        <p className="max-w-[44ch] text-base">The AI reads your instruction. The geometry engine moves the wall, and every edit is a version you can undo.</p>
      </aside>
      <main className="flex flex-col items-center justify-center gap-6 p-6">
        <Link href="/" aria-label="AEC Studio home" className="lg:hidden">
          <Logo className="text-base" />
        </Link>
        {children}
      </main>
    </div>
  );
}
