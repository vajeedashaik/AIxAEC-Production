import { expect } from "@playwright/test";

import { USERS } from "../env";
import { Api, apiFor, command, shot, signIn, token, test } from "../helpers";

test("10. a second user gets 404 for the first user's project, plan and model", async ({ page, request, browser }) => {
  await signIn(page, USERS.alice);
  const { projectId, floorplanId, url } = await (await apiFor(page, request)).readyPlan("Private");

  const other = await (await browser.newContext()).newPage();
  await signIn(other, USERS.bob);
  const bob = new Api(request, await token(other));
  for (const path of [`/projects/${projectId}`, `/floorplans/${floorplanId}`, `/floorplans/${floorplanId}/model`, `/floorplans/${floorplanId}/history`]) {
    expect((await bob.call("GET", path)).status, path).toBe(404);
  }
  expect((await bob.call("POST", `/floorplans/${floorplanId}/commands`, { data: { instruction: "delete the door" } })).status).toBe(404);
  expect((await bob.call<{ items: unknown[] }>("GET", "/projects")).body.items).toHaveLength(0);

  await other.goto(url);
  await expect(other.getByTestId("workspace-message")).toBeVisible();
  await shot(other, "10-other-user-404");
});

test("11. two tabs editing: the second apply gets the stale-model message", async ({ page, request, context }) => {
  await signIn(page, USERS.alice);
  const { url } = await (await apiFor(page, request)).readyPlan("Two tabs");
  const second = await context.newPage();
  await page.goto(url);
  await second.goto(url);

  await command(page, "rename the kitchen to galley");
  await command(second, "rename the bathroom to wet room");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByTestId("version-chip")).toContainText("2");
  await second.getByRole("button", { name: "Apply" }).click();
  await expect(second.getByTestId("stale")).toBeVisible();
  await expect(second.getByTestId("version-chip")).toContainText("2");
  await shot(second, "11-stale-model");
});
