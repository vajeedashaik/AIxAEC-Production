import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { Analysis, CommandInput, ComplianceReport, CostEstimate, Takeoff } from "@/contracts";
import { API_URL, makeQueryClient } from "@/lib/api";
import fixture from "@/mocks/fixtures/analysis.apartment.json";
import { server } from "@/mocks/node";

import { AnalyzePanel, ComplianceView, CostView, LayoutsView, TakeoffView } from "./analysis";
import { AskPanel } from "./ask";
import { toCsv } from "./csv";

const analysis = fixture as unknown as Analysis;
const FP = "c0d50567-abaa-43fd-ba84-0b9e05790fa7";

function Wrap({ children }: { children: ReactNode }) {
  const [client] = useState(makeQueryClient);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("toCsv", () => {
  it("quotes separators and neutralises spreadsheet formulas from drawing labels", () => {
    expect(toCsv([["=HYPERLINK(1)", 'a,"b"', 3]])).toBe(`'=HYPERLINK(1),"a,""b""",3\r\n`);
  });
});

describe("views", () => {
  it("shows the bill of quantities with units", () => {
    render(<TakeoffView takeoff={analysis.takeoff as Takeoff} />);
    expect(screen.getByText("Total wall length")).toBeInTheDocument();
    expect(screen.getByText("64.4 m")).toBeInTheDocument();
    expect(screen.getByText("Bricks")).toBeInTheDocument();
  });

  it("leads with failures and hides passes until asked", async () => {
    const onPick = vi.fn();
    render(<ComplianceView report={analysis.compliance as ComplianceReport} onPick={onPick} />);
    expect(screen.queryByText(/minimum floor area/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /door route to an exit/ }));
    expect(onPick).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: /Show \d+ passed/ }));
    expect(screen.getAllByText(/minimum floor area/).length).toBeGreaterThan(0);
  });

  it("sends edited rates", async () => {
    const onRates = vi.fn();
    render(<CostView estimate={analysis.estimate as CostEstimate} onRates={onRates} busy={false} />);
    await userEvent.click(screen.getByText("Edit rates"));
    const concrete = screen.getByLabelText("Concrete per m3");
    await userEvent.clear(concrete);
    await userEvent.type(concrete, "200");
    await userEvent.click(screen.getByRole("button", { name: "Apply rates" }));
    expect(onRates.mock.calls[0][0]).toMatchObject({ concrete_per_m3: 200, currency: "INR" });
  });

  it("previews a suggested layout through the normal command path", async () => {
    const onPreview = vi.fn<(c: CommandInput) => void>();
    render(<Wrap><LayoutsView floorplanId={FP} readOnly={false} onPreview={onPreview} /></Wrap>);
    await userEvent.click(screen.getByRole("button", { name: "Make kitchen larger." }));
    await userEvent.click((await screen.findAllByRole("button", { name: "Preview on plan" }))[0]);
    expect(onPreview.mock.calls[0][0]).toMatchObject({ operation: "RESIZE_ROOM", mode: "EXPAND" });
  });
});

describe("AnalyzePanel", () => {
  const props = { active: true, floorplanId: FP, version: 1, readOnly: false, onCalibrate: vi.fn(), onPick: vi.fn(), onPreview: vi.fn(), onFurniture: vi.fn() };

  it("loads the takeoff", async () => {
    render(<Wrap><AnalyzePanel {...props} /></Wrap>);
    expect(await screen.findByTestId("takeoff")).toBeInTheDocument();
  });

  it("asks for a scale instead of inventing numbers", async () => {
    server.use(http.post(`${API_URL}/v1/floorplans/${FP}/analysis`, () => HttpResponse.json({ needs_scale: true, takeoff: null, compliance: null, estimate: null, interior: null, structural: null })));
    render(<Wrap><AnalyzePanel {...props} /></Wrap>);
    expect(await screen.findByTestId("analysis-needs-scale")).toBeInTheDocument();
  });
});

describe("AskPanel", () => {
  it("answers and reports the elements to highlight", async () => {
    const onAnswer = vi.fn();
    server.use(http.post(`${API_URL}/v1/floorplans/${FP}/ask`, () => HttpResponse.json({ status: "ANSWERED", answer: "LIVING is the largest room.", element_ids: ["r1"], source: "rules" })));
    render(<Wrap><AskPanel floorplanId={FP} version={1} onAnswer={onAnswer} /></Wrap>);
    await userEvent.click(screen.getByRole("button", { name: "Which room has the largest area?" }));
    expect(await screen.findByTestId("answer")).toHaveTextContent("LIVING is the largest room.");
    await waitFor(() => expect(onAnswer).toHaveBeenCalledWith(["r1"]));
  });
});
