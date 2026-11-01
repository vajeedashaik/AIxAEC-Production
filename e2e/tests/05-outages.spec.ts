import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { expect } from "@playwright/test";

import { API_URL, USERS } from "../env";
import { apiFor, command, shot, signIn, test } from "../helpers";

// Stops real compose containers. Opt in, so a run against a stack you care about never kills it.
test.skip(!process.env.E2E_COMPOSE, "set E2E_COMPOSE=1 to stop and start compose services");

const root = fileURLToPath(new URL("../..", import.meta.url));
const compose = (...args: string[]) => execFileSync("docker", ["compose", ...args], { cwd: root, stdio: "pipe" });

test("12a. language down: the edit is refused at parse, the rest of the app keeps working", async ({ page, request }) => {
  await signIn(page, USERS.alice);
  const api = await apiFor(page, request);
  const { floorplanId, url } = await api.readyPlan("Language outage");
  compose("stop", "language");
  try {
    await page.goto(url);
    await command(page, "rename the kitchen to galley");
    const rejection = page.getByTestId("rejection");
    await expect(rejection).toHaveAttribute("data-stage", "parse");
    await expect(rejection).toContainText("The command assistant is offline");
    await shot(page, "12-language-down");
    expect((await api.call("GET", `/floorplans/${floorplanId}/model`)).status).toBe(200);
    expect((await request.get(`${API_URL}/healthz`)).status()).toBe(200);
  } finally {
    compose("start", "language");
  }
});

test("12b. vision down: the job fails cleanly and a retry succeeds", async ({ page, request }) => {
  await signIn(page, USERS.alice);
  const api = await apiFor(page, request);
  const projectId = await api.project("Vision outage");
  compose("stop", "vision");
  let floorplanId: string;
  try {
    floorplanId = await api.upload(projectId);
    await api.processed(floorplanId, "FAILED");
  } finally {
    compose("up", "-d", "--wait", "vision");
  }
  await page.goto(`/projects/${projectId}`);
  await shot(page, "12-vision-failed");
  expect((await api.call("POST", `/floorplans/${floorplanId}/process`)).status).toBe(202);
  await api.processed(floorplanId);
});
