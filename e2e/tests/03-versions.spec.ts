import { readFileSync } from "node:fs";

import { expect } from "@playwright/test";

import { USERS } from "../env";
import { apiFor, command, fixture, shot, signIn, test } from "../helpers";

type Res = { status: string; version: number; transcript?: string | null; command?: { operation: string } | null };
type History = { versions: { version: number; discarded: boolean; is_head: boolean; origin: string }[] };

test("7. voice: a spoken WAV is transcribed and applied through the same pipeline", async ({ page, request }) => {
  await signIn(page, USERS.alice);
  const api = await apiFor(page, request);
  const { floorplanId } = await api.readyPlan("Voice");
  const audio = { name: "rename.wav", mimeType: "audio/wav", buffer: readFileSync(fixture("rename-bathroom.wav")) };

  const dry = await api.call<Res>("POST", `/floorplans/${floorplanId}/commands/voice`, { multipart: { audio, dry_run: "true" } });
  expect(dry.status).toBe(200);
  expect(dry.body.transcript?.toLowerCase()).toContain("bathroom");
  expect(dry.body.status).toBe("PREVIEW");

  const applied = await api.call<Res>("POST", `/floorplans/${floorplanId}/commands/voice`, { multipart: { audio, expected_version: "1" } });
  expect([applied.body.status, applied.body.version, applied.body.command?.operation]).toEqual(["APPLIED", 2, "RENAME_ROOM"]);
});

test("8–9. undo ×2 → redo → fresh edit discards; re-process then undo returns to the edits", async ({ page, request }) => {
  await signIn(page, USERS.alice);
  const api = await apiFor(page, request);
  const { floorplanId, url } = await api.readyPlan("Versions");
  const edit = (instruction: string, expected_version: number) =>
    api.call<Res>("POST", `/floorplans/${floorplanId}/commands`, { data: { instruction, expected_version } });
  expect((await edit("rename the kitchen to galley", 1)).body.version).toBe(2);
  expect((await edit("rename the bathroom to wet room", 2)).body.version).toBe(3);

  await page.goto(url);
  const chip = page.getByTestId("version-chip");
  await expect(chip).toContainText("3");
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(chip).toContainText("2");
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(chip).toContainText("1");
  await page.getByRole("button", { name: "Redo" }).click();
  await expect(chip).toContainText("2");

  await command(page, "rename the hall to entry");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(chip).toContainText("4");
  await page.getByRole("tab", { name: "History" }).click();
  await expect(page.locator("[data-discarded]")).toHaveCount(1); // v3 left the branch
  await shot(page, "08-history-discarded");

  // 9. Re-process makes a new PROCESSING version; one undo goes back to the edited model.
  expect((await api.call("POST", `/floorplans/${floorplanId}/process`)).status).toBe(202);
  await api.processed(floorplanId);
  const history = (await api.call<History>("GET", `/floorplans/${floorplanId}/history`)).body;
  const head = history.versions.find((v) => v.is_head)!;
  expect([head.version, head.origin]).toEqual([5, "PROCESSING"]);
  const undo = await api.call<Res>("POST", `/floorplans/${floorplanId}/model/undo?expected_version=5`);
  expect([undo.body.status, undo.body.version]).toEqual(["APPLIED", 4]);
});
