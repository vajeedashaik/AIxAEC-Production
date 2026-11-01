import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { clerk } from "@clerk/testing/playwright";
import { test as base, expect, type APIRequestContext, type Page } from "@playwright/test";

/** Every test fails on a Content-Security-Policy violation (blocked Clerk, API or Storage request). */
export const test = base.extend<{ cspGuard: void }>({
  cspGuard: [
    async ({ context }, use) => {
      const violations: string[] = [];
      context.on("console", (m) => m.type() === "error" && /Content Security Policy/i.test(m.text()) && violations.push(m.text()));
      await use();
      expect(violations, "CSP violations").toEqual([]);
    },
    { auto: true },
  ],
});

import { API_URL } from "./env";

export const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));
export const shot = (page: Page, name: string) =>
  page.screenshot({ path: fileURLToPath(new URL(`../apps/web/qa/p7/${name}.png`, import.meta.url)) });

export async function signIn(page: Page, email: string) {
  await page.goto("/");
  await clerk.signIn({ page, emailAddress: email });
}

/** A fresh Clerk session token: the same bearer the web app sends. */
export const token = (page: Page) => page.evaluate(async () => (await window.Clerk.session!.getToken())!);

export class Api {
  constructor(private request: APIRequestContext, private bearer: string) {}

  async call<T = unknown>(method: string, path: string, init: { data?: unknown; multipart?: Record<string, unknown> } = {}) {
    const res = await this.request.fetch(`${API_URL}/v1${path}`, {
      method,
      headers: { Authorization: `Bearer ${this.bearer}` },
      data: init.data,
      multipart: init.multipart as never,
    });
    return { status: res.status(), body: (res.status() === 204 ? null : await res.json()) as T };
  }

  async project(name: string): Promise<string> {
    const { status, body } = await this.call<{ id: string }>("POST", "/projects", { data: { name } });
    expect(status).toBe(201);
    return body.id;
  }

  async upload(projectId: string, file = "apartment.png"): Promise<string> {
    const { status, body } = await this.call<{ id: string }>("POST", `/projects/${projectId}/floorplans`, {
      multipart: { file: { name: file, mimeType: "image/png", buffer: readFileSync(fixture(file)) } },
    });
    expect(status).toBe(201);
    return body.id;
  }

  /** Polls the job until it settles. */
  async processed(floorplanId: string, want: "COMPLETED" | "FAILED" = "COMPLETED") {
    await expect
      .poll(async () => (await this.call<{ status: string }>("GET", `/floorplans/${floorplanId}/job`)).body.status, {
        timeout: 90_000,
        intervals: [1_000],
      })
      .toBe(want);
  }

  /** A project with one processed apartment plan; returns the workspace URL. */
  async readyPlan(name: string) {
    const projectId = await this.project(name);
    const floorplanId = await this.upload(projectId);
    await this.processed(floorplanId);
    return { projectId, floorplanId, url: `/projects/${projectId}/floorplans/${floorplanId}` };
  }
}

export async function apiFor(page: Page, request: APIRequestContext) {
  return new Api(request, await token(page));
}

/** Types into the command bar and presses Enter (preview). */
export async function command(page: Page, text: string) {
  const input = page.getByTestId("command-bar").getByRole("textbox");
  await input.fill(text);
  await input.press("Enter");
}
