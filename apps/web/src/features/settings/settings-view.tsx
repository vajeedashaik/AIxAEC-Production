"use client";

import { useAuth, UserProfile } from "@clerk/nextjs";
import { useTheme } from "next-themes";
import { useSyncExternalStore, type ReactNode } from "react";

import { PageHeader } from "@/components/composites";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { clerkAppearance } from "@/lib/clerk-appearance";
import { CLERK_ENABLED } from "@/lib/clerk";
import { usePreference } from "@/lib/preferences";

function Choice<T extends string>({ label, hint, value, options, onChange }: { label: string; hint: string; value: T | undefined; options: { value: T; label: string }[]; onChange: (value: T) => void }) {
  const labelId = `setting-${label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-3">
      <div className="min-w-0">
        <p id={labelId} className="text-sm font-medium">
          {label}
        </p>
        <p className="max-w-[52ch] text-ui text-muted-foreground">{hint}</p>
      </div>
      <ToggleGroup type="single" variant="outline" aria-labelledby={labelId} value={value} onValueChange={(v) => v && onChange(v as T)}>
        {options.map((o) => (
          <ToggleGroupItem key={o.value} value={o.value} className="px-3">
            {o.label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-x-8 gap-y-2 border-t py-6 lg:grid-cols-[12rem_1fr]">
      <h2 className="text-base font-medium">{title}</h2>
      <div className="min-w-0 divide-y">{children}</div>
    </section>
  );
}

const noSubscribe = () => () => {};

export function SettingsView() {
  const { theme, setTheme } = useTheme();
  const [density, setDensity] = usePreference("density");
  const [units, setUnits] = usePreference("units");
  // next-themes only knows the stored theme in the browser; leave the toggle unset during SSR.
  const mounted = useSyncExternalStore(noSubscribe, () => true, () => false);

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-6 md:px-6">
      <PageHeader title="Settings" className="mb-6" />
      <Section title="Appearance">
        <Choice label="Theme" hint="System follows your operating system." value={mounted ? theme : undefined} onChange={setTheme} options={[{ value: "system", label: "System" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} />
        <Choice label="Density" hint="Compact fits more rows and tools on screen, in lists and in the workspace." value={density} onChange={setDensity} options={[{ value: "comfortable", label: "Comfortable" }, { value: "compact", label: "Compact" }]} />
      </Section>
      <Section title="Units">
        <Choice
          label="Measurements"
          hint="Metric applies only to plans with a known scale. Unscaled plans always show pixels, because pixels can't be converted without one."
          value={units}
          onChange={setUnits}
          options={[{ value: "metric", label: "mm and m²" }, { value: "px", label: "Pixels" }]}
        />
      </Section>
      {CLERK_ENABLED && <AccountSection />}
    </div>
  );
}

/** Only inside <ClerkProvider>. Hidden when signed out (e.g. the dev mock bypass), where <UserProfile/> can't render. */
function AccountSection() {
  const { isSignedIn } = useAuth();
  if (!isSignedIn) return null;
  return (
    <Section title="Account">
      {/* Hash routing: /settings isn't a catch-all route. */}
      <UserProfile routing="hash" appearance={{ ...clerkAppearance, elements: { ...clerkAppearance.elements, cardBox: { boxShadow: "none", width: "100%", border: "1px solid var(--border)" }, rootBox: { width: "100%" } } }} />
    </Section>
  );
}
