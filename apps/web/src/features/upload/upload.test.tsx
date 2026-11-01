import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/mocks/node";
import { api, errorBody, FetchXhr, PROJECT_ID, renderApp, stubBrowserApis } from "@/test/render";

import { UploadDropzone } from "./dropzone";
import { fileProblem, MAX_UPLOAD_BYTES } from "./validate";

const png = (name = "plan.png", bytes = 10) => new File([new Uint8Array(bytes)], name, { type: "image/png" });

beforeAll(stubBrowserApis);
beforeEach(() => {
  FetchXhr.sent = [];
});
const sentNames = () => FetchXhr.sent.map((f) => (f.get("file") as File).name);

describe("fileProblem", () => {
  it("accepts PNG, JPG and PDF", () => {
    for (const type of ["image/png", "image/jpeg", "application/pdf"]) expect(fileProblem({ name: "a", size: 1, type })).toBeNull();
  });
  it("rejects other types, naming what is allowed", () => {
    expect(fileProblem({ name: "a.dwg", size: 1, type: "application/acad" })).toMatch(/PNG, JPG or PDF/);
  });
  it("rejects empty files", () => {
    expect(fileProblem({ name: "a.png", size: 0, type: "image/png" })).toMatch(/empty/);
  });
  it("allows exactly 25 MB and rejects one byte more", () => {
    expect(fileProblem({ name: "a.png", size: MAX_UPLOAD_BYTES, type: "image/png" })).toBeNull();
    expect(fileProblem({ name: "a.png", size: MAX_UPLOAD_BYTES + 1, type: "image/png" })).toMatch(/25 MB/);
  });
  it("uses the extension only when the browser reports no type", () => {
    expect(fileProblem({ name: "PLAN.PDF", size: 1, type: "" })).toBeNull();
    expect(fileProblem({ name: "plan.exe", size: 1, type: "" })).not.toBeNull();
    expect(fileProblem({ name: "plan.png", size: 1, type: "text/html" })).not.toBeNull(); // extension can't override a wrong type
  });
});

describe("UploadDropzone", () => {
  const input = () => screen.getByLabelText<HTMLInputElement>("Choose floor plan files");
  const pick = async (...files: File[]) => userEvent.setup({ applyAccept: false }).upload(input(), files);

  it("shows a rejection message without calling the API", async () => {
    const spy = vi.fn();
    server.use(http.post(api(`/projects/${PROJECT_ID}/floorplans`), () => (spy(), HttpResponse.json({}, { status: 500 }))));
    renderApp(<UploadDropzone projectId={PROJECT_ID} />);
    await pick(new File(["x"], "notes.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("isn't a PNG, JPG or PDF");
    expect(spy).not.toHaveBeenCalled();
  });

  it("uploads a valid file and surfaces the API's warnings", async () => {
    const plan = { id: "x", warnings: ["Only page 1 of 3 processed"] };
    server.use(http.post(api(`/projects/${PROJECT_ID}/floorplans`), () => HttpResponse.json(plan, { status: 201 })));
    renderApp(<UploadDropzone projectId={PROJECT_ID} />);
    await pick(png());
    expect(await screen.findByText("Only page 1 of 3 processed")).toBeInTheDocument();
    expect(screen.getByLabelText("Uploaded")).toBeInTheDocument();
  });

  it("reports progress from the XHR while uploading", async () => {
    let finish!: (r: Response) => void;
    server.use(http.post(api(`/projects/${PROJECT_ID}/floorplans`), () => new Promise<Response>((r) => (finish = r))));
    renderApp(<UploadDropzone projectId={PROJECT_ID} />);
    await pick(png());
    expect(await screen.findByRole("progressbar", { name: "Uploading plan.png" })).toBeInTheDocument();
    finish(HttpResponse.json({ warnings: [] }, { status: 201 }));
    expect(await screen.findByLabelText("Uploaded")).toBeInTheDocument();
  });

  it("uploads several files one at a time, in order", async () => {
    let inFlight = 0;
    let peak = 0;
    server.use(
      http.post(api(`/projects/${PROJECT_ID}/floorplans`), async () => {
        peak = Math.max(peak, ++inFlight);
        await new Promise((r) => setTimeout(r, 5));
        inFlight--;
        return HttpResponse.json({ warnings: [] }, { status: 201 });
      }),
    );
    renderApp(<UploadDropzone projectId={PROJECT_ID} />);
    await pick(png("a.png"), png("b.png"), png("c.png"));
    await waitFor(() => expect(screen.getAllByLabelText("Uploaded")).toHaveLength(3));
    expect(sentNames()).toEqual(["a.png", "b.png", "c.png"]);
    expect(peak).toBe(1);
  });

  it("maps a server rejection to readable copy, then retries on request", async () => {
    let fail = true;
    server.use(http.post(api(`/projects/${PROJECT_ID}/floorplans`), () => (fail ? HttpResponse.json(errorBody("payload_too_large"), { status: 413 }) : HttpResponse.json({ warnings: [] }, { status: 201 }))));
    renderApp(<UploadDropzone projectId={PROJECT_ID} />);
    await pick(png());
    expect(await screen.findByRole("alert")).toHaveTextContent("Upload a file of 25 MB or less.");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Retry plan.png" }));
    expect(await screen.findByLabelText("Uploaded")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps the queue moving after one file fails", async () => {
    server.use(
      http.post(api(`/projects/${PROJECT_ID}/floorplans`), () => {
        return sentNames().at(-1) === "bad.png" ? HttpResponse.json(errorBody("internal_error"), { status: 500 }) : HttpResponse.json({ warnings: [] }, { status: 201 });
      }),
    );
    renderApp(<UploadDropzone projectId={PROJECT_ID} />);
    await pick(png("bad.png"), png("good.png"));
    expect(await screen.findByLabelText("Uploaded")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("removes a dismissed item from the queue", async () => {
    renderApp(<UploadDropzone projectId={PROJECT_ID} />);
    await pick(new File(["x"], "notes.txt", { type: "text/plain" }));
    await userEvent.click(await screen.findByRole("button", { name: "Dismiss notes.txt" }));
    expect(screen.queryByText("notes.txt")).not.toBeInTheDocument();
  });
});
