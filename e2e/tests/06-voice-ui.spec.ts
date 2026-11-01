import { expect } from "@playwright/test";

import { USERS } from "../env";
import { apiFor, fixture, shot, signIn, test } from "../helpers";

// Chromium plays the WAV as the microphone; the workspace records, uploads with dry_run and shows what it heard.
test.use({
  launchOptions: {
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-audio-capture=${fixture("rename-bathroom.wav")}`],
  },
  permissions: ["microphone"],
});

test("7b. voice in the browser: hold V, release, the transcript lands in the command bar", async ({ page, request }) => {
  await signIn(page, USERS.alice);
  const { url } = await (await apiFor(page, request)).readyPlan("Voice UI");
  await page.goto(url);
  await expect(page.getByTestId("floorplan-canvas")).toBeVisible();

  await page.getByTestId("floorplan-canvas").click({ position: { x: 5, y: 5 } }); // focus the page, not an input
  await page.keyboard.down("v");
  await expect(page.getByTestId("recording")).toBeVisible();
  await page.waitForTimeout(3_500); // the fixture is ~3 s of speech
  await page.keyboard.up("v");

  await expect(page.getByTestId("heard")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("command-bar").getByRole("textbox")).toHaveValue(/bathroom/i);
  await shot(page, "07-voice-heard");
});
