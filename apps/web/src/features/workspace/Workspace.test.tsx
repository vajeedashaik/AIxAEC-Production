import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import type { RejectStage } from "@/contracts";
import { API_URL, makeQueryClient } from "@/lib/api";
import { server } from "@/mocks/node";

import { installDomStubs } from "../viewer/test-env";
import { REJECT_TITLES } from "./CommandBar";
import { Workspace } from "./Workspace";

const FP = "c0d50567-abaa-43fd-ba84-0b9e05790fa7";
const PROJECT = "a3e1b2c4-d5f6-4a7b-8c9d-e0f1a2b3c4d5";
const V1 = `${API_URL}/v1/floorplans/${FP}`;
const MOVE = "move the wall between the kitchen and the living room 300 mm left";
const EMPTY = { model: null, changes: null, command: null, summary: null, question: null, candidates: [], stage: null, detail: null, transcript: null, edit_id: null };

// jsdom has no layout: the real panels hit-test every pointer at (0,0) as a separator drag.
vi.mock("@/components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => null,
}));
vi.mock("next/link", () => ({ default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a> }));

function Harness() {
  const [version, setVersion] = useState<number | null>(null);
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <Workspace projectId={PROJECT} floorplanId={FP} version={version} onVersionChange={setVersion} />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

let fetchSpy: { mock: { calls: [RequestInfo | URL, RequestInit?][] } };
const bodiesTo = (suffix: string) =>
  fetchSpy.mock.calls
    .filter(([url, init]) => String(url).split("?")[0].endsWith(suffix) && (init as RequestInit | undefined)?.method === "POST")
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)));

beforeEach(() => {
  installDomStubs();
  fetchSpy = vi.spyOn(globalThis, "fetch");
});
afterEach(() => vi.restoreAllMocks());

async function ready() {
  const user = userEvent.setup();
  render(<Harness />);
  await screen.findByText("v1 · HEAD");
  await screen.findByRole("button", { name: "Undo" });
  return { user, input: screen.getByRole("textbox", { name: "Describe an edit" }) };
}

describe("Workspace", () => {
  it("previews with Enter, applies the resolved command, and bumps the version", async () => {
    const { user, input } = await ready();
    await user.type(input, `${MOVE}{Enter}`);
    const card = await screen.findByTestId("preview-card");
    expect(card).toHaveTextContent("Moved wall 300 mm left");
    expect(screen.getByTestId("preview-layer").querySelector('[data-change="modified-before"]')).toBeInTheDocument();
    expect(bodiesTo("/commands/interpret")).toEqual([{ instruction: MOVE, expected_version: 1 }]);

    await user.click(within(card).getByRole("button", { name: "Apply" }));
    await screen.findByText("v2 · HEAD");
    const [applied] = bodiesTo("/commands");
    expect(applied.expected_version).toBe(1);
    expect(applied.command).toMatchObject({ operation: "MOVE_WALL", direction: "LEFT", distance: { value: 300, unit: "mm" } });
    expect(applied.command.target_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(applied.instruction).toBeUndefined();
    expect(input).toHaveValue("");
  });

  it("applies directly with Ctrl+Enter", async () => {
    const { user, input } = await ready();
    await user.type(input, MOVE);
    await user.keyboard("{Control>}{Enter}{/Control}");
    await screen.findByText("v2 · HEAD");
    expect(bodiesTo("/commands/interpret")).toEqual([]);
    expect(bodiesTo("/commands")).toEqual([{ instruction: MOVE, expected_version: 1 }]);
  });

  it("discards a preview without sending anything", async () => {
    const { user, input } = await ready();
    await user.type(input, `${MOVE}{Enter}`);
    await user.click(within(await screen.findByTestId("preview-card")).getByRole("button", { name: "Discard" }));
    expect(screen.queryByTestId("preview-card")).toBeNull();
    expect(screen.queryByTestId("preview-layer")).toBeNull();
    expect(bodiesTo("/commands")).toEqual([]);
  });

  it("asks which element, and the picked chip re-sends the structured command with target_id", async () => {
    const { user, input } = await ready();
    await user.type(input, "move the kitchen wall 300 mm left{Enter}");
    const box = await screen.findByTestId("clarification");
    expect(box).toHaveTextContent("Which wall do you mean?");
    const chips = within(box).getAllByRole("button").filter((b) => b.getAttribute("aria-label") !== "Dismiss");
    expect(chips.length).toBeGreaterThanOrEqual(2);
    const vertical = chips.find((c) => c.textContent?.startsWith("vertical"))!;
    await user.hover(vertical);
    expect(document.querySelector("[data-highlight]")).toBeInTheDocument();
    await user.click(vertical);
    await screen.findByTestId("preview-card");
    const sent = bodiesTo("/commands/interpret")[1];
    expect(sent.instruction).toBeUndefined();
    expect(sent.command).toMatchObject({ operation: "MOVE_WALL", direction: "LEFT", distance: { value: 300, unit: "mm" } });
    expect(sent.command.target_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("re-sends a structured clarification with the same command and only the target swapped", async () => {
    server.use(
      http.post(`${V1}/commands/interpret`, async ({ request }) => {
        const body = (await request.json()) as { command?: { target_id?: string } };
        if (body.command?.target_id === "w-1") return HttpResponse.json({ ...EMPTY, status: "REJECTED", version: 1, stage: "geometry", detail: "ok" });
        return HttpResponse.json({ ...EMPTY, status: "CLARIFICATION", version: 1, question: "Which one?", candidates: [{ id: "w-1", kind: "wall", label: "first", x: 1, y: 1 }, { id: "w-2", kind: "wall", label: "second", x: 2, y: 2 }] });
      }),
    );
    const { user } = await ready();
    await user.click(screen.getAllByRole("button").find((b) => b.textContent?.includes("LIVING"))!);
    await user.click(await screen.findByRole("button", { name: "Rename" }));
    await user.click(screen.getByRole("button", { name: "Preview" }));
    await user.click(within(await screen.findByTestId("clarification")).getByRole("button", { name: "first" }));
    await screen.findByTestId("rejection");
    const [first, second] = bodiesTo("/commands/interpret");
    expect(second.command).toEqual({ ...first.command, target_id: "w-1" });
  });

  it.each(Object.keys(REJECT_TITLES) as RejectStage[])("explains a %s rejection", async (stage) => {
    server.use(http.post(`${V1}/commands/interpret`, () => HttpResponse.json({ ...EMPTY, status: "REJECTED", version: 1, stage, detail: `Detail for ${stage}.` })));
    const { user, input } = await ready();
    await user.type(input, "do the thing{Enter}");
    const alert = await screen.findByTestId("rejection");
    expect(alert).toHaveAttribute("data-stage", stage);
    expect(alert).toHaveTextContent(REJECT_TITLES[stage]);
    expect(alert).toHaveTextContent(`Detail for ${stage}.`);
  });

  it("titles a language outage as offline, not as a misunderstanding", async () => {
    const detail = "The command assistant is unavailable right now. Your plan was not changed.";
    server.use(http.post(`${V1}/commands/interpret`, () => HttpResponse.json({ ...EMPTY, status: "REJECTED", version: 1, stage: "parse", detail })));
    const { user, input } = await ready();
    await user.type(input, "rename the kitchen{Enter}");
    const alert = await screen.findByTestId("rejection");
    expect(alert).toHaveTextContent("The command assistant is offline");
    expect(alert).not.toHaveTextContent(REJECT_TITLES.parse);
  });

  it("offers Set scale when a rejection needs one, and opens the flow", async () => {
    server.use(
      http.get(`${V1}/model`, async () => {
        const { mockApi } = await import("@/mocks/db");
        const env = mockApi.getModel(FP);
        env.model.coordinate_system.mm_per_pixel = null;
        env.insights.metric = null;
        return HttpResponse.json(env);
      }),
      http.post(`${V1}/commands/interpret`, () => HttpResponse.json({ ...EMPTY, status: "REJECTED", version: 1, stage: "semantic_validation", detail: "Set a scale first to use millimetres." })),
    );
    const { user, input } = await ready();
    await user.type(input, `${MOVE}{Enter}`);
    const alert = await screen.findByTestId("rejection");
    await user.click(within(alert).getByRole("button", { name: "Set scale" }));
    expect(screen.getByTestId("inspector-empty")).toHaveTextContent("Click a wall whose real length you know");
  });

  it("refetches on a stale model and keeps the user's text", async () => {
    server.use(http.post(`${V1}/commands/interpret`, () => HttpResponse.json({ error: { code: "stale_model", message: "The plan changed since you loaded it.", details: {} } }, { status: 409 })));
    const { user, input } = await ready();
    const gets = () => fetchSpy.mock.calls.filter(([u, i]) => String(u).endsWith(`${FP}/model`) && !(i as RequestInit)?.method?.startsWith("P")).length;
    const before = gets();
    await user.type(input, `${MOVE}{Enter}`);
    expect(await screen.findByTestId("stale")).toHaveTextContent("The plan changed; here's the latest");
    expect(input).toHaveValue(MOVE);
    await waitFor(() => expect(gets()).toBeGreaterThan(before));
  });

  it("gates Undo and Redo on history and steps through versions", async () => {
    const { user, input } = await ready();
    const undo = screen.getByRole("button", { name: "Undo" });
    const redo = screen.getByRole("button", { name: "Redo" });
    expect(undo).toBeDisabled();
    expect(redo).toBeDisabled();
    await user.type(input, MOVE);
    await user.keyboard("{Control>}{Enter}{/Control}");
    await screen.findByText("v2 · HEAD");
    await waitFor(() => expect(undo).toBeEnabled());
    await user.click(undo);
    await screen.findByText("v1 · HEAD");
    await waitFor(() => expect(redo).toBeEnabled());
    expect(undo).toBeDisabled();
    await act(async () => {
      await user.click(document.body);
      await user.keyboard("{Control>}{Shift>}z{/Shift}{/Control}");
    });
    await screen.findByText("v2 · HEAD");
  });

  it("opens an old version read-only from history and goes back to HEAD", async () => {
    const { user, input } = await ready();
    await user.type(input, MOVE);
    await user.keyboard("{Control>}{Enter}{/Control}");
    await screen.findByText("v2 · HEAD");
    await user.click(screen.getByRole("button", { name: "History" }));
    const panel = await screen.findByTestId("history");
    await waitFor(() => expect(within(panel).getByText("v1")).toBeInTheDocument());
    expect(within(panel).getAllByTestId("edit-entry")[0]).toHaveTextContent(MOVE);
    await user.click(within(panel).getByText("v1"));
    expect(await screen.findByTestId("read-only-bar")).toHaveTextContent("Viewing v1, read-only");
    expect(screen.getByTestId("version-chip")).toHaveTextContent(/^v1$/);
    expect(screen.getByRole("textbox", { name: "Describe an edit" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Back to HEAD" }));
    await screen.findByText("v2 · HEAD");
  });

  it("shows insights with metric values when scaled", async () => {
    const { user } = await ready();
    await user.click(screen.getByRole("tab", { name: "Insights" }));
    const panel = await screen.findByTestId("insights");
    expect(panel).toHaveTextContent("m²");
    expect(panel).not.toHaveTextContent("Calibrate to see m²");
  });

  it("selects from the outline and shows the inspector", async () => {
    const { user } = await ready();
    await user.click(screen.getAllByRole("button").find((b) => b.textContent === "KITCHEN")!);
    const inspector = await screen.findByTestId("inspector");
    expect(inspector).toHaveTextContent("KITCHEN");
    expect(inspector).toHaveTextContent("Kitchen");
    expect(inspector).toHaveTextContent("Inferred");
    expect(within(inspector).getByTestId("selection-actions")).toBeInTheDocument();
  });

  it("shows the processing state while there is no model yet", async () => {
    server.use(http.get(V1, async () => {
      const { mockApi } = await import("@/mocks/db");
      return HttpResponse.json({ ...mockApi.getFloorplan(FP), status: "PROCESSING", current_model_version: null });
    }));
    render(<Harness />);
    expect(await screen.findByText("Reading the drawing")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See the timeline" })).toHaveAttribute("href", `/projects/${PROJECT}`);
  });

  it("shows a not-found state for an unknown plan", async () => {
    server.use(http.get(V1, () => HttpResponse.json({ error: { code: "not_found", message: "Not found.", details: {} } }, { status: 404 })));
    render(<Harness />);
    expect(await screen.findByText("This plan doesn't exist")).toBeInTheDocument();
  });
});

describe("voice", () => {
  const TRANSCRIPT = "move the wall between the kitchen and the living room 300 mm left";
  class FakeRecorder {
    static isTypeSupported = (t: string) => t === "audio/webm;codecs=opus";
    static last: FakeRecorder | null = null;
    state = "inactive";
    mimeType: string;
    ondataavailable: ((e: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;
    constructor(_s: MediaStream, opts?: { mimeType?: string }) {
      this.mimeType = opts?.mimeType ?? "";
      FakeRecorder.last = this;
    }
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      this.ondataavailable?.({ data: new Blob(["audio"], { type: this.mimeType }) });
      this.onstop?.();
    }
  }
  const track = { stop: vi.fn() };

  beforeEach(() => {
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    // jsdom FormData can't be parsed by MSW's node multipart reader; answer without reading the body.
    server.use(http.post(`${V1}/commands/voice`, () => HttpResponse.json({ ...EMPTY, status: "PREVIEW", version: 1, transcript: TRANSCRIPT })));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("records with opus, uploads as a dry run and shows the editable transcript", async () => {
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
    const { user, input } = await ready();
    await user.click(screen.getByRole("button", { name: "Speak an edit" }));
    const stop = await screen.findByRole("button", { name: "Stop recording" });
    expect(FakeRecorder.last?.mimeType).toBe("audio/webm;codecs=opus");
    expect(input).toHaveAttribute("placeholder", "Listening…");
    await user.click(stop);
    await waitFor(() => expect(input).toHaveValue(TRANSCRIPT));
    expect(screen.getByTestId("heard")).toHaveTextContent("Heard:");
    expect(track.stop).toHaveBeenCalled();
    const call = fetchSpy.mock.calls.find(([u]) => String(u).endsWith("/commands/voice"))!;
    const form = (call[1] as RequestInit).body as FormData;
    expect(form.get("dry_run")).toBe("true");
    expect(form.get("expected_version")).toBe("1");
    expect(bodiesTo("/commands")).toEqual([]);
  });

  it("explains a denied microphone and keeps typing available", async () => {
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockRejectedValue(Object.assign(new Error("denied"), { name: "NotAllowedError" })) } });
    const { user, input } = await ready();
    await user.click(screen.getByRole("button", { name: "Speak an edit" }));
    expect(await screen.findByTestId("command-error")).toHaveTextContent("Microphone access is blocked");
    expect(input).toBeEnabled();
    expect(screen.getByRole("button", { name: "Speak an edit" })).toBeInTheDocument();
  });

  it("push-to-talk: holding V records and releasing it stops", async () => {
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) } });
    const { user, input } = await ready();
    await user.click(document.body);
    await user.keyboard("{v>}");
    await screen.findByRole("button", { name: "Stop recording" });
    await user.keyboard("{/v}");
    await waitFor(() => expect(input).toHaveValue(TRANSCRIPT));
  });
});
