"use client";

import { useCallback, useRef, useState } from "react";

import type { Candidate, CommandInput, CommandRequest, CommandResponse, RejectStage } from "@/contracts";
import { ApiError, type ApiClient } from "@/lib/api";

import { commandFromInstruction, withTarget } from "./commands";

/** What the user asked for: words or a structured command. Exactly one, like CommandRequest. */
export type CommandSource = { instruction: string } | { command: CommandInput };

// CommandRequest.command is an open object in the contract; our typed commands are a subset of it.
const toRequest = (source: CommandSource, expected_version: number | null): CommandRequest =>
  "instruction" in source ? { instruction: source.instruction, expected_version } : { command: source.command as unknown as Record<string, unknown>, expected_version };

export type Flow =
  | { state: "idle" }
  | { state: "busy"; label: string }
  | { state: "preview"; response: CommandResponse }
  | { state: "clarification"; question: string; candidates: Candidate[]; source: CommandSource; response: CommandResponse }
  | { state: "rejected"; stage: RejectStage; detail: string }
  | { state: "stale" }
  | { state: "error"; message: string };

interface Options {
  api: ApiClient;
  floorplanId: string;
  headVersion: number | null;
  /** A new HEAD exists; the response carries it. */
  onApplied(response: CommandResponse): void;
  /** HEAD moved under us: refetch. */
  onStale(): void;
}

export function useCommandFlow({ api, floorplanId, headVersion, onApplied, onStale }: Options) {
  const [flow, setFlow] = useState<Flow>({ state: "idle" });
  // Only the latest request may update the flow; Discard or a new request orphans the one in flight.
  const seq = useRef(0);

  const fail = useCallback(
    (e: unknown) => {
      if (e instanceof ApiError && e.code === "stale_model") {
        onStale();
        setFlow({ state: "stale" });
      } else setFlow({ state: "error", message: e instanceof Error ? e.message : "Something went wrong." });
    },
    [onStale],
  );

  const route = useCallback(
    (res: CommandResponse, source: CommandSource) => {
      switch (res.status) {
        case "PREVIEW":
          if (!res.model) return setFlow({ state: "error", message: "The server sent a preview without a plan." });
          return setFlow({ state: "preview", response: res });
        case "APPLIED":
          setFlow({ state: "idle" });
          return onApplied(res);
        case "CLARIFICATION":
          return setFlow({ state: "clarification", question: res.question ?? "Which one do you mean?", candidates: res.candidates ?? [], source, response: res });
        case "REJECTED":
          return setFlow({ state: "rejected", stage: res.stage ?? "semantic_validation", detail: res.detail ?? "That edit can't be applied." });
      }
    },
    [onApplied],
  );

  const send = useCallback(
    async (source: CommandSource, persist: boolean) => {
      const id = ++seq.current;
      setFlow({ state: "busy", label: persist ? "Applying" : "Previewing" });
      const body = toRequest(source, headVersion);
      try {
        const res = await (persist ? api.applyCommand(floorplanId, body) : api.interpretCommand(floorplanId, body));
        if (id === seq.current) route(res, source);
      } catch (e) {
        if (id === seq.current) fail(e);
      }
    },
    [api, fail, floorplanId, headVersion, route],
  );

  const preview = useCallback((source: CommandSource) => send(source, false), [send]);

  /** Commit what is on screen. Sends the resolved command so what was previewed is exactly what gets applied. */
  const apply = useCallback(
    async (source?: CommandSource) => {
      if (source) return send(source, true);
      if (flow.state !== "preview" || !flow.response.command) return;
      const id = ++seq.current;
      const response = flow.response;
      setFlow({ state: "busy", label: "Applying" });
      try {
        const res = await api.applyCommand(floorplanId, toRequest({ command: response.command as CommandInput }, response.version));
        if (id === seq.current) route(res, { command: response.command as CommandInput });
      } catch (e) {
        if (id === seq.current) fail(e);
      }
    },
    [api, fail, floorplanId, flow, route, send],
  );

  const pick = useCallback(
    (candidate: Candidate) => {
      if (flow.state !== "clarification") return;
      const { source, response } = flow;
      const command =
        "command" in source
          ? withTarget(source.command as unknown as Record<string, unknown>, candidate.id)
          : response.command
            ? withTarget(response.command as unknown as Record<string, unknown>, candidate.id)
            : commandFromInstruction(source.instruction, candidate);
      if (!command) return setFlow({ state: "error", message: "I can't finish that from the words alone. Select the element and use its actions, or rephrase naming it." });
      return send({ command }, false);
    },
    [flow, send],
  );

  const discard = useCallback(() => {
    seq.current++;
    setFlow({ state: "idle" });
  }, []);

  /** Report a failure from a neighbouring request (voice, undo) in the same place. */
  const report = useCallback((e: unknown) => fail(e), [fail]);

  return { flow, preview, apply, pick, discard, report };
}
