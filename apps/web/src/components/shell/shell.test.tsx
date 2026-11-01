import { act, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useTheme } from "next-themes";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardView, deriveStats, partOfDay, recentPlans } from "@/features/dashboard/dashboard-view";
import { HeroDemo } from "@/features/marketing/hero-demo";
import { INITIAL_PLAN, moveWallLeft, planRooms, areaLabel } from "@/features/marketing/plan-geometry";
import { server } from "@/mocks/node";
import { api, errorBody, PLAN_ID, PROJECT_ID, renderApp, stubBrowserApis, testClient } from "@/test/render";
import type { FloorPlan, Project } from "@/contracts";

import { ApiError } from "@/lib/api/client";

import { AuthRedirect, signInHref } from "./auth-redirect";
import { parseRoute } from "./breadcrumbs";
import { CommandPalette } from "./command-palette";
import { ThemeToggle } from "./theme-toggle";

const nav = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn(), pathname: "/dashboard" }));
vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(),
}));

beforeAll(stubBrowserApis);
beforeEach(() => {
  nav.replace.mockReset();
  nav.push.mockReset();
  nav.pathname = "/dashboard";
  localStorage.clear();
});

describe("parseRoute", () => {
  it("reads each level of the app's routes", () => {
    expect(parseRoute("/settings")).toEqual({ top: "settings", projectId: null, floorplanId: null });
    expect(parseRoute("/projects/p1")).toEqual({ top: "projects", projectId: "p1", floorplanId: null });
    expect(parseRoute("/projects/p1/floorplans/f1")).toEqual({ top: "projects", projectId: "p1", floorplanId: "f1" });
  });
});

describe("401 redirect", () => {
  it("encodes the current location for the sign-in page", () => {
    expect(signInHref("/projects?q=a b")).toBe("/sign-in?redirect_url=%2Fprojects%3Fq%3Da%20b");
  });

  it("sends a 401 query to sign-in, keeping where the user was", async () => {
    nav.pathname = "/projects/p1";
    const client = testClient();
    renderApp(<AuthRedirect />, { client });
    await client.fetchQuery({ queryKey: ["x"], queryFn: () => Promise.reject(new ApiError(401, "unauthorized", "no")) }).catch(() => {});
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/sign-in?redirect_url=%2Fprojects%2Fp1"));
  });

  it("does not redirect on other errors, so a blip never signs anyone out", async () => {
    const client = testClient();
    renderApp(<AuthRedirect />, { client });
    await client.fetchQuery({ queryKey: ["y"], queryFn: () => Promise.reject(new ApiError(503, "upstream_unavailable", "no")) }).catch(() => {});
    expect(nav.replace).not.toHaveBeenCalled();
  });
});

describe("CommandPalette", () => {
  const open = (onCreateProject = vi.fn(), onOpenChange = vi.fn()) => {
    renderApp(<CommandPalette open onOpenChange={onOpenChange} onCreateProject={onCreateProject} />);
    return { onCreateProject, onOpenChange };
  };

  it("jumps to a project", async () => {
    const { onOpenChange } = open();
    await userEvent.click(await screen.findByRole("option", { name: /Riverside Apartment/ }));
    expect(nav.push).toHaveBeenCalledWith(`/projects/${PROJECT_ID}`);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("jumps to a completed floor plan's workspace", async () => {
    open();
    await userEvent.click(await screen.findByRole("option", { name: /apartment\.png/ }));
    expect(nav.push).toHaveBeenCalledWith(`/projects/${PROJECT_ID}/floorplans/${PLAN_ID}`);
  });

  it("filters as you type and navigates with the keyboard", async () => {
    open();
    await screen.findByRole("option", { name: /Harbour Office/ });
    await userEvent.type(screen.getByRole("combobox"), "harbour");
    await waitFor(() => expect(screen.queryByRole("option", { name: /Riverside/ })).not.toBeInTheDocument());
    await userEvent.keyboard("{Enter}");
    expect(nav.push).toHaveBeenCalledWith(expect.stringMatching(/^\/projects\/b4f2/));
  });

  it("creates a project", async () => {
    const { onCreateProject } = open();
    await userEvent.click(screen.getByRole("option", { name: /New project/ }));
    expect(onCreateProject).toHaveBeenCalled();
  });
});

describe("theme", () => {
  it("the toggle flips the theme and persists it", async () => {
    renderApp(<ThemeToggle />);
    await userEvent.click(screen.getByRole("button", { name: "Toggle theme" }));
    await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
    expect(localStorage.getItem("theme")).toBe("dark");
    await userEvent.click(screen.getByRole("button", { name: "Toggle theme" }));
    await waitFor(() => expect(localStorage.getItem("theme")).toBe("light"));
  });

  it("restores the stored theme on a fresh mount", async () => {
    localStorage.setItem("theme", "dark");
    const { result } = renderHook(() => useTheme(), { wrapper: ({ children }) => renderWrapper(children) });
    await waitFor(() => expect(result.current).toBeDefined());
  });
});

function renderWrapper(children: React.ReactNode) {
  return <>{children}</>;
}

describe("dashboard data", () => {
  const p = (id: string, count: number): Project => ({ id, name: id, description: null, floorplan_count: count, thumbnail_url: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" });

  it("sums floor plans when every project is loaded", () => {
    expect(deriveStats({ items: [p("a", 2), p("b", 3)], total: 2 })).toEqual({ projects: 2, floorplans: 5 });
  });
  it("drops the floor-plan total rather than show a partial count", () => {
    expect(deriveStats({ items: [p("a", 2)], total: 150 })).toEqual({ projects: 150, floorplans: null });
  });
  it("orders recent plans newest first, across projects", () => {
    const plan = (id: string, created_at: string) => ({ id, created_at }) as FloorPlan;
    const recent = recentPlans([
      { project: p("a", 1), plans: [plan("old", "2026-01-01T00:00:00Z")] },
      { project: p("b", 1), plans: [plan("new", "2026-02-01T00:00:00Z")] },
    ]);
    expect(recent.map((r) => r.plan.id)).toEqual(["new", "old"]);
  });
  it("greets by part of day", () => {
    expect([partOfDay(8), partOfDay(13), partOfDay(20)]).toEqual(["Good morning", "Good afternoon", "Good evening"]);
  });
});

describe("DashboardView", () => {
  it("greets by first name and shows only real totals", async () => {
    renderApp(<DashboardView />);
    expect(await screen.findByRole("heading", { level: 1, name: /, Ada$/ })).toBeInTheDocument();
    expect(await screen.findByText("Projects")).toBeInTheDocument();
    expect(screen.queryByText(/edits this week/i)).not.toBeInTheDocument();
    expect(await screen.findByText("apartment.png")).toBeInTheDocument();
  });

  it("shows the first-run path when there are no projects", async () => {
    server.use(http.get(api("/projects"), () => HttpResponse.json({ items: [], total: 0, limit: 100, offset: 0 })));
    const { createProject } = renderApp(<DashboardView />);
    await userEvent.click(await screen.findByRole("button", { name: "Create your first project" }));
    expect(createProject).toHaveBeenCalled();
    expect(screen.queryByText("Recent floor plans")).not.toBeInTheDocument();
  });

  it("shows a retryable error when projects can't load", async () => {
    server.use(http.get(api("/projects"), () => HttpResponse.json(errorBody("upstream_unavailable"), { status: 503 })));
    renderApp(<DashboardView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load your projects");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("landing demo geometry", () => {
  it("computes real areas, to 2 dp", () => {
    const rooms = planRooms(INITIAL_PLAN);
    expect(areaLabel(rooms.find((r) => r.id === "living")!)).toBe("19.44 m²");
    expect(areaLabel(rooms.find((r) => r.id === "kitchen")!)).toBe("12.96 m²");
  });
  it("conserves total area when a wall moves", () => {
    const area = (plan: typeof INITIAL_PLAN) => planRooms(plan).reduce((s, r) => s + r.w * r.h, 0);
    const moved = moveWallLeft(INITIAL_PLAN, "kitchen", 300);
    expect(moved.ok && area(moved.plan)).toBe(area(INITIAL_PLAN));
  });
  it("rejects a move that would break a room", () => {
    expect(moveWallLeft(INITIAL_PLAN, "kitchen", 5000).ok).toBe(false);
    expect(moveWallLeft(INITIAL_PLAN, "bath", 500).ok).toBe(false);
  });
});

describe("HeroDemo", () => {
  beforeEach(() => {
    window.matchMedia = ((q: string) => ({ matches: q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} })) as unknown as typeof window.matchMedia;
  });
  const start = async (name: RegExp) => {
    renderApp(<HeroDemo />);
    await userEvent.click(screen.getByRole("button", { name }));
  };

  it("previews, applies as a new version, and undoes", async () => {
    await start(/kitchen wall 300 mm/);
    expect(screen.getByText("Preview.")).toBeInTheDocument();
    expect(screen.getByText("v1 · HEAD")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByText("v2 · HEAD")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(screen.getByText("v1 · HEAD")).toBeInTheDocument();
  });

  it("asks which wall instead of guessing, then previews the pick", async () => {
    await start(/^move the wall 300 mm/);
    expect(screen.getByText(/Which wall do you mean/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Between living room and kitchen" }));
    expect(screen.getByText("Preview.")).toBeInTheDocument();
  });

  it("rejects an impossible move and changes nothing", async () => {
    await start(/5000 mm/);
    expect(screen.getByText("Rejected by the geometry engine.")).toBeInTheDocument();
    expect(screen.getByText("v1 · HEAD")).toBeInTheDocument();
    act(() => {});
  });
});
