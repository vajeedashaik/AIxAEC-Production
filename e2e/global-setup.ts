import { createClerkClient } from "@clerk/backend";
import { clerkSetup } from "@clerk/testing/playwright";

import { loadEnv, USERS } from "./env";

/** Fresh Clerk test users every run, so quotas and old projects never leak between runs. */
export default async function globalSetup() {
  loadEnv();
  await clerkSetup();
  const clerk = createClerkClient({ secretKey: process.env.CLERK_SECRET_KEY! });
  const { data: existing } = await clerk.users.getUserList({ emailAddress: Object.values(USERS), limit: 10 });
  for (const u of existing) await clerk.users.deleteUser(u.id);
  for (const email of [USERS.alice, USERS.bob]) {
    await clerk.users.createUser({ emailAddress: [email], password: `e2e-${crypto.randomUUID()}`, skipPasswordChecks: true });
  }
}
