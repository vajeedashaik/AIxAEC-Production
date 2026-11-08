import { expect, type Page } from "@playwright/test";

import { USERS } from "../env";
import { apiFor, shot, signIn, test } from "../helpers";

const openView = async (page: Page, name: string) => {
  await page.getByRole("combobox", { name: "Analysis" }).click();
  await page.getByRole("option", { name }).click();
};

test("13. analyze: BOQ, cost, compliance, interior, suggestions", async ({ page, request }) => {
  await signIn(page, USERS.alice);
  const { url } = await (await apiFor(page, request)).readyPlan("Analysis");
  await page.goto(url);
  await expect(page.getByTestId("version-chip")).toContainText("1");

  await page.getByRole("tab", { name: "Analyze" }).click();
  await expect(page.getByTestId("takeoff")).toContainText("Bricks");
  await expect(page.getByTestId("takeoff")).toContainText("Total wall length");
  await shot(page, "13-takeoff");

  await openView(page, "Cost estimate");
  await expect(page.getByTestId("construction-cost")).toContainText("INR");
  await shot(page, "13-cost");

  await openView(page, "Code compliance");
  await expect(page.getByTestId("compliance-summary")).toContainText("passed");
  await shot(page, "13-compliance");

  await openView(page, "Interior design");
  await page.getByLabel(/furniture pieces on the plan/).click();
  await expect(page.getByTestId("preview-layer")).toBeAttached();
  await shot(page, "13-interior");

  await openView(page, "Structural suggestions");
  await expect(page.getByTestId("structure")).toContainText("Lighting improvement");
});

test("14. ask: the chatbot answers from the model", async ({ page, request }) => {
  await signIn(page, USERS.alice);
  const { url } = await (await apiFor(page, request)).readyPlan("Ask");
  await page.goto(url);
  await page.getByRole("tab", { name: "Ask" }).click();
  await page.getByRole("button", { name: "How many bedrooms?" }).click();
  await expect(page.getByTestId("answer").first()).toContainText("1 bedroom");
  await page.getByLabel("Ask about this plan").fill("Which room has the largest area?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("answer").nth(1)).toContainText("LIVING");
  await shot(page, "14-ask");
});

test("15. layout suggestion: preview, apply, undo", async ({ page, request }) => {
  await signIn(page, USERS.alice);
  const { url } = await (await apiFor(page, request)).readyPlan("Layouts");
  await page.goto(url);
  await page.getByRole("tab", { name: "Analyze" }).click();
  await openView(page, "Layout suggestions");
  await page.getByRole("button", { name: "Make kitchen larger." }).click();
  await expect(page.getByTestId("layout-option").first()).toBeVisible();
  await shot(page, "15-layouts");

  await page.getByRole("button", { name: "Preview on plan" }).first().click();
  await expect(page.getByTestId("preview-card")).toBeVisible();
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByTestId("version-chip")).toContainText("2");

  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByTestId("version-chip")).toContainText("1");
});
