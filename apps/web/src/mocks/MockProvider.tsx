"use client";

import dynamic from "next/dynamic";
import type { ReactNode } from "react";

export const MOCKING = process.env.NEXT_PUBLIC_API_MOCKING === "on";

declare global {
  // Resolved once the MSW worker is active; the API client awaits it (src/lib/api/client.ts).
  var __AEC_MOCK_READY__: Promise<void> | undefined;
  var __AEC_MOCK_RESOLVE__: (() => void) | undefined;
}

// Created at module load, before any query can fire, so no request slips past the worker.
if (MOCKING && typeof window !== "undefined" && !globalThis.__AEC_MOCK_READY__) {
  globalThis.__AEC_MOCK_READY__ = new Promise<void>((resolve) => (globalThis.__AEC_MOCK_RESOLVE__ = resolve));
}

// ssr:false keeps `msw/browser` (null under the node export condition) out of the server bundle.
const MockWorker = dynamic(() => import("./MockWorker"), { ssr: false });

/** Starts the MSW worker when NEXT_PUBLIC_API_MOCKING=on; children render immediately either way. */
export function MockProvider({ children }: { children: ReactNode }) {
  return (
    <>
      {MOCKING && <MockWorker />}
      {children}
    </>
  );
}
