// Clerk runs whenever a publishable key exists, and always in production (missing keys then fail closed).
// In development without keys the app still boots (e.g. against MSW); run `npx clerk@latest init --accountless`
// in apps/web to get temporary dev keys written to .env.local.
export const CLERK_ENABLED =
  !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || process.env.NODE_ENV === "production";
