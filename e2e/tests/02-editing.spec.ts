import { expect, type Page } from "@playwright/test";

import { USERS } from "../env";
import { apiFor, command, shot, signIn, test } from "../helpers";

const pickWall = async (page: Page) => {
  await page.getByLabel("Search elements").fill("wall");
  await page.getByRole("button", { name: /^(Vertical|Horizontal) wall/ }).first().click();
};

test("3 + 6b. unscaled plan: mm needs a scale, then Set scale switches insights to m²", async ({ page, request }) => {
  await signIn(page, USERS.alice);
  const api = await apiFor(page, request);
  const projectId = await api.project("Unscaled");
  const floorplanId = await api.upload(projectId, "two_room.png");
  await api.processed(floorplanId);
  await page.goto(`/projects/${projectId}/floorplans/${floorplanId}`);
  await expect(page.getByTestId("floorplan-canvas")).toBeVisible();

  await command(page, "move the shared wall 300 mm left");
  await expect(page.getByTestId("rejection")).toContainText(/scale/i);
  await shot(page, "06-needs-scale");

  // The rejection's own "Set scale" arms the form; it opens as soon as a wall is selected.
  await page.getByTestId("rejection").getByRole("button", { name: "Set scale" }).click();
  await pickWall(page);
  await page.getByLabel("Real length of this wall (mm)").fill("3600");
  await page.getByRole("button", { name: "Preview" }).click();
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByTestId("version-chip")).toContainText("2");
  await page.getByRole("tab", { name: "Insights" }).click();
  await expect(page.getByTestId("insights")).toContainText("m²");
  await shot(page, "03-scaled-insights");
});

test("4–6. preview ghost → apply, clarification → pick, nonsense → friendly UNKNOWN", async ({ page, request }) => {
  await signIn(page, USERS.alice);
  const { url } = await (await apiFor(page, request)).readyPlan("Edits");
  await page.goto(url);
  await expect(page.getByTestId("version-chip")).toContainText("1");

  await command(page, "move the wall between the kitchen and the living room 300 mm left");
  await expect(page.getByTestId("preview-card")).toBeVisible();
  await expect(page.getByTestId("preview-layer")).toBeAttached();
  await shot(page, "04-preview-ghost");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByTestId("version-chip")).toContainText("2");

  await command(page, "delete the door");
  const clarification = page.getByTestId("clarification");
  await expect(clarification).toBeVisible();
  await shot(page, "05-clarification");
  await clarification.getByRole("button").filter({ hasText: /door/i }).first().click();
  await expect(page.getByTestId("preview-card")).toBeVisible();
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByTestId("version-chip")).toContainText("3");

  await command(page, "make it look like a banana");
  await expect(page.getByTestId("rejection")).toContainText(/didn.t understand|couldn.t/i);
  await shot(page, "06-unknown");
});
