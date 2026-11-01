/** Development without Clerk keys. Production without keys fails closed before reaching this (src/lib/clerk.ts). */
export function ClerkNotConfigured() {
  return (
    <div className="flex max-w-sm flex-col gap-2 rounded-lg border bg-card p-6">
      <h1 className="text-base font-medium">Clerk isn&apos;t configured</h1>
      <p className="text-sm text-muted-foreground">
        Run <code className="numeric">npx clerk@latest init --accountless</code> in <code className="numeric">apps/web</code> for temporary dev keys, or add your keys to{" "}
        <code className="numeric">.env.local</code>.
      </p>
    </div>
  );
}
