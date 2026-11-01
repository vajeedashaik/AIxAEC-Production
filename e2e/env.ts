import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// "+clerk_test" addresses verify with code 424242 on a Clerk development instance and never send mail.
export const USERS = {
  alice: "aec-e2e-alice+clerk_test@example.com",
  bob: "aec-e2e-bob+clerk_test@example.com",
  signup: "aec-e2e-signup+clerk_test@example.com",
} as const;

export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

/** Clerk keys default to apps/web/.env.local so a local run needs no extra setup. Real env vars win. */
export function loadEnv() {
  const file = fileURLToPath(new URL("../apps/web/.env.local", import.meta.url));
  if (existsSync(file)) {
    for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*"?(.*?)"?\s*$/);
      if (m && !process.env[m[1]]) process.env[m[1]] = m[2];
    }
  }
  process.env.CLERK_PUBLISHABLE_KEY ??= process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  if (!process.env.CLERK_PUBLISHABLE_KEY || !process.env.CLERK_SECRET_KEY) {
    throw new Error("e2e needs Clerk dev keys: CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY (or apps/web/.env.local).");
  }
}
