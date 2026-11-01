import { setupClerkTestingToken } from "@clerk/testing/playwright";
import { expect } from "@playwright/test";

import { USERS } from "../env";
import { fixture, shot, test } from "../helpers";

test("sign up → first-run dashboard → create project → upload → 8-stage timeline → workspace", async ({ page }) => {
  // 1. Sign up through the real Clerk form. "+clerk_test" addresses verify with 424242.
  await setupClerkTestingToken({ page });
  await page.goto("/sign-up");
  await page.getByRole("textbox", { name: "Email address" }).fill(USERS.signup);
  await page.getByRole("textbox", { name: "Password" }).fill(`E2e-${crypto.randomUUID()}`);
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Verify your email" })).toBeVisible({ timeout: 30_000 });
  await page.keyboard.type("424242"); // the first code box has focus
  await page.waitForURL("**/dashboard", { timeout: 30_000 });

  await expect(page.getByRole("heading", { name: "Start with one drawing" })).toBeVisible();
  await shot(page, "01-dashboard-first-run");

  await page.getByRole("button", { name: "Create your first project" }).click();
  await page.getByLabel("Name").fill("E2E apartment");
  await page.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL(/\/projects\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { name: "E2E apartment" })).toBeVisible();

  // 2. Upload → the eight stages run → open the workspace.
  await page.getByLabel("Choose floor plan files").setInputFiles(fixture("apartment.png"));
  const stages = page.getByRole("list", { name: "Processing stages" });
  await expect(stages).toBeVisible({ timeout: 30_000 });
  await expect(stages.getByRole("listitem")).toHaveCount(8);
  await shot(page, "02-processing-timeline");
  await page.getByRole("link", { name: "Open plan" }).first().click({ timeout: 60_000 });
  await expect(page.getByTestId("floorplan-canvas")).toBeVisible();
  await expect(page.getByTestId("version-chip")).toContainText("1");
  await shot(page, "02-workspace");
});
