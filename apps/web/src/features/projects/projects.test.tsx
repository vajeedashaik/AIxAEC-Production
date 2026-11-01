import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { FloorPlan, Project } from "@/contracts";
import { mockApi } from "@/mocks/db";
import { server } from "@/mocks/node";
import { api, EMPTY_PROJECT_ID, errorBody, PLAN_ID, PROJECT_ID, renderApp, stubBrowserApis } from "@/test/render";

import { FloorplanList } from "./floorplan-list";
import { ProjectDetail } from "./project-detail";
import { filterAndSort, ProjectsView } from "./projects-view";

const nav = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn(), search: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  usePathname: () => "/projects",
  useSearchParams: () => new URLSearchParams(nav.search),
}));

beforeAll(stubBrowserApis);
beforeEach(() => {
  nav.replace.mockReset();
  nav.push.mockReset();
  nav.search = "";
});

const project = (over: Partial<Project>): Project => ({ id: "p", name: "P", description: null, floorplan_count: 0, thumbnail_url: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", ...over });

describe("filterAndSort", () => {
  const list = [project({ id: "1", name: "Bravo", description: "tower", floorplan_count: 1, updated_at: "2026-03-01T00:00:00Z" }), project({ id: "2", name: "Alpha", floorplan_count: 5, updated_at: "2026-01-01T00:00:00Z" })];
  it("sorts by each key", () => {
    expect(filterAndSort(list, "", "name")[0].id).toBe("2");
    expect(filterAndSort(list, "", "updated")[0].id).toBe("1");
    expect(filterAndSort(list, "", "plans")[0].id).toBe("2");
  });
  it("searches name and description, ignoring case", () => {
    expect(filterAndSort(list, "ALPHA", "name").map((p) => p.id)).toEqual(["2"]);
    expect(filterAndSort(list, "tower", "name").map((p) => p.id)).toEqual(["1"]);
  });
});

describe("ProjectsView", () => {
  it("lists projects from the API", async () => {
    renderApp(<ProjectsView />);
    expect(await screen.findByRole("link", { name: "Riverside Apartment" })).toHaveAttribute("href", `/projects/${PROJECT_ID}`);
    expect(screen.getByRole("link", { name: "Harbour Office Fit-out" })).toBeInTheDocument();
  });

  it("shows skeletons, then an empty state whose action opens the create dialog", async () => {
    server.use(http.get(api("/projects"), () => HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 })));
    const { createProject } = renderApp(<ProjectsView />);
    expect(screen.getByRole("status", { name: "Loading projects" })).toBeInTheDocument();
    const empty = (await screen.findByRole("heading", { name: "No projects yet" })).parentElement!.parentElement!;
    await userEvent.click(within(empty).getByRole("button", { name: "New project" }));
    expect(createProject).toHaveBeenCalled();
  });

  it("shows an error with a working retry", async () => {
    let fail = true;
    server.use(http.get(api("/projects"), () => (fail ? HttpResponse.json(errorBody("internal_error"), { status: 500 }) : HttpResponse.json({ items: [project({ name: "Back again" })], total: 1, limit: 20, offset: 0 }))));
    renderApp(<ProjectsView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load projects");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Back again" })).toBeInTheDocument();
  });

  it("offers no retry for a final error", async () => {
    server.use(http.get(api("/projects"), () => HttpResponse.json(errorBody("forbidden"), { status: 403 })));
    renderApp(<ProjectsView />);
    await screen.findByRole("alert");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("reads the search from the URL and shows a clearable no-match state", async () => {
    nav.search = "q=zzz";
    renderApp(<ProjectsView />);
    expect(await screen.findByRole("heading", { name: "Nothing matches “zzz”" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(nav.replace).toHaveBeenCalledWith("/projects", { scroll: false });
  });

  it("writes search text and layout to the URL", async () => {
    renderApp(<ProjectsView />);
    await screen.findByRole("link", { name: "Riverside Apartment" });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search projects" }), "r");
    expect(nav.replace).toHaveBeenLastCalledWith("/projects?q=r", { scroll: false });
    await userEvent.click(screen.getByRole("radio", { name: "List" }));
    expect(nav.replace).toHaveBeenLastCalledWith("/projects?view=list", { scroll: false });
  });

  it("pages through the API", async () => {
    const offsets: (string | null)[] = [];
    server.use(
      http.get(api("/projects"), ({ request }) => {
        const offset = new URL(request.url).searchParams.get("offset");
        offsets.push(offset);
        return HttpResponse.json({ items: [project({ id: `p${offset}`, name: `Page at ${offset}` })], total: 45, limit: 20, offset: Number(offset) });
      }),
    );
    nav.search = "page=2";
    renderApp(<ProjectsView />);
    expect(await screen.findByRole("link", { name: "Page at 20" })).toBeInTheDocument();
    expect(offsets).toEqual(["20"]);
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(nav.replace).toHaveBeenCalledWith("/projects?page=3", { scroll: false });
  });

  it("renames optimistically and persists", async () => {
    renderApp(<ProjectsView />);
    await userEvent.click(await screen.findByRole("button", { name: "More actions for Riverside Apartment" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Rename" }));
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Riverside Loft");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("link", { name: "Riverside Loft" })).toBeInTheDocument();
    expect(mockApi.getProject(PROJECT_ID).name).toBe("Riverside Loft");
  });

  it("validates the rename dialog before calling the API", async () => {
    const spy = vi.fn();
    server.use(http.patch(api(`/projects/${PROJECT_ID}`), () => (spy(), HttpResponse.json({}))));
    renderApp(<ProjectsView />);
    await userEvent.click(await screen.findByRole("button", { name: "More actions for Riverside Apartment" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Rename" }));
    await userEvent.clear(await screen.findByRole("textbox", { name: "Name" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Give the project a name.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("rolls a rename back when the API refuses", async () => {
    let refuse = false;
    server.use(http.patch(api(`/projects/${PROJECT_ID}`), () => (refuse ? HttpResponse.json(errorBody("internal_error"), { status: 500 }) : undefined)));
    refuse = true;
    renderApp(<ProjectsView />);
    await userEvent.click(await screen.findByRole("button", { name: "More actions for Riverside Apartment" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Rename" }));
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Nope");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(await screen.findByRole("link", { name: "Riverside Apartment" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Nope" })).not.toBeInTheDocument();
  });

  it("deletes only after confirmation", async () => {
    renderApp(<ProjectsView />);
    await userEvent.click(await screen.findByRole("button", { name: "More actions for Harbour Office Fit-out" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(mockApi.listProjects().total).toBe(2);
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete project" }));
    await waitFor(() => expect(mockApi.listProjects().total).toBe(1));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Harbour Office Fit-out" })).not.toBeInTheDocument());
  });

  it("cancelling the confirm dialog deletes nothing", async () => {
    renderApp(<ProjectsView />);
    await userEvent.click(await screen.findByRole("button", { name: "More actions for Harbour Office Fit-out" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Cancel" }));
    expect(mockApi.listProjects().total).toBe(2);
  });
});

describe("ProjectDetail", () => {
  it("edits the name inline with Enter", async () => {
    renderApp(<ProjectDetail projectId={PROJECT_ID} />);
    await userEvent.click(await screen.findByRole("button", { name: /Edit project name/ }));
    const field = screen.getByRole("textbox", { name: "project name" });
    await userEvent.clear(field);
    await userEvent.type(field, "New name{Enter}");
    await waitFor(() => expect(mockApi.getProject(PROJECT_ID).name).toBe("New name"));
  });

  it("cancels inline editing with Escape", async () => {
    renderApp(<ProjectDetail projectId={PROJECT_ID} />);
    await userEvent.click(await screen.findByRole("button", { name: /Edit project name/ }));
    await userEvent.type(screen.getByRole("textbox", { name: "project name" }), "xx{Escape}");
    expect(screen.queryByRole("textbox", { name: "project name" })).not.toBeInTheDocument();
    expect(mockApi.getProject(PROJECT_ID).name).toBe("Riverside Apartment");
  });

  it("keeps the field open with a message when the name is blank", async () => {
    renderApp(<ProjectDetail projectId={PROJECT_ID} />);
    await userEvent.click(await screen.findByRole("button", { name: /Edit project name/ }));
    const field = screen.getByRole("textbox", { name: "project name" });
    await userEvent.clear(field);
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Give the project a name.");
    expect(mockApi.getProject(PROJECT_ID).name).toBe("Riverside Apartment");
  });

  it("shows the not-found copy for a project that isn't there", async () => {
    renderApp(<ProjectDetail projectId="00000000-0000-4000-8000-000000000000" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("It may have been deleted");
  });
});

describe("FloorplanList", () => {
  const plan = (over: Partial<FloorPlan>): FloorPlan => ({ ...mockApi.listFloorplans(PROJECT_ID)[0], ...over });
  const fresh = (id = "fp-fresh"): FloorPlan => {
    const base = plan({ id, original_filename: "fresh.png", status: "PENDING", current_model_version: null, warnings: [] });
    return { ...base, latest_job: { ...base.latest_job!, floorplan_id: id, status: "PENDING", attempts: 0, stages: [], started_at: null, finished_at: null } };
  };

  it("links a completed plan to P6's workspace route", async () => {
    renderApp(<FloorplanList projectId={PROJECT_ID} />);
    expect(await screen.findByRole("link", { name: "Open plan" })).toHaveAttribute("href", `/projects/${PROJECT_ID}/floorplans/${PLAN_ID}`);
  });

  it("shows an empty state when the project has no plans", async () => {
    renderApp(<FloorplanList projectId={EMPTY_PROJECT_ID} />);
    expect(await screen.findByRole("heading", { name: "No floor plans yet" })).toBeInTheDocument();
  });

  it("offers Start processing on a fresh PENDING job, and treats a 409 as already queued", async () => {
    const spy = vi.fn();
    server.use(
      http.get(api(`/projects/${PROJECT_ID}/floorplans`), () => HttpResponse.json([fresh()])),
      http.get(api("/floorplans/fp-fresh/job"), () => HttpResponse.json(fresh().latest_job)),
      http.post(api("/floorplans/fp-fresh/process"), () => (spy(), HttpResponse.json(errorBody("already_processing"), { status: 409 }))),
    );
    renderApp(<FloorplanList projectId={PROJECT_ID} />);
    await userEvent.click(await screen.findByRole("button", { name: "Start processing" }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the 8-stage timeline while processing, with no Start button", async () => {
    const running = fresh();
    running.status = "PROCESSING";
    Object.assign(running.latest_job!, { status: "PROCESSING", started_at: new Date().toISOString(), stages: [{ name: "preprocess", status: "ok", duration_ms: 120, error: null, detail: {} }] });
    server.use(
      http.get(api(`/projects/${PROJECT_ID}/floorplans`), () => HttpResponse.json([running])),
      http.get(api("/floorplans/fp-fresh/job"), () => HttpResponse.json(running.latest_job)),
    );
    renderApp(<FloorplanList projectId={PROJECT_ID} />);
    const stages = await screen.findByRole("list", { name: "Processing stages" });
    expect(within(stages).getAllByRole("listitem")).toHaveLength(8);
    expect(within(stages).getByText("120 ms")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start processing" })).not.toBeInTheDocument();
  });

  it("shows the failure and retries a FAILED plan", async () => {
    const failed = fresh();
    failed.status = "FAILED";
    Object.assign(failed.latest_job!, { status: "FAILED", error_message: "No walls detected.", started_at: new Date().toISOString() });
    const spy = vi.fn();
    server.use(
      http.get(api(`/projects/${PROJECT_ID}/floorplans`), () => HttpResponse.json([failed])),
      http.post(api("/floorplans/fp-fresh/process"), () => (spy(), HttpResponse.json({ ...failed.latest_job, status: "PENDING", error_message: null, started_at: null }, { status: 202 }))),
      http.get(api("/floorplans/fp-fresh/job"), () => HttpResponse.json({ ...failed.latest_job, status: "PENDING", error_message: null, started_at: null })),
    );
    renderApp(<FloorplanList projectId={PROJECT_ID} />);
    expect(await screen.findByText("No walls detected.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
  });

  it("surfaces plan warnings", async () => {
    server.use(http.get(api(`/projects/${PROJECT_ID}/floorplans`), () => HttpResponse.json([plan({ warnings: ["Only page 1 of 3 processed"] })])));
    renderApp(<FloorplanList projectId={PROJECT_ID} />);
    expect(await screen.findByText("Only page 1 of 3 processed")).toBeInTheDocument();
  });

  it("picks up the finished status when polling sees the job complete", async () => {
    const done = plan({});
    let list: FloorPlan[] = [{ ...fresh(PLAN_ID), status: "PROCESSING" }];
    server.use(
      http.get(api(`/projects/${PROJECT_ID}/floorplans`), () => HttpResponse.json(list)),
      http.get(api(`/floorplans/${PLAN_ID}/job`), () => {
        list = [done];
        return HttpResponse.json(done.latest_job);
      }),
    );
    renderApp(<FloorplanList projectId={PROJECT_ID} />);
    expect(await screen.findByRole("link", { name: "Open plan" }, { timeout: 4000 })).toBeInTheDocument();
  });
});
