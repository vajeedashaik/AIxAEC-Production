import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { ThemeProvider } from "next-themes";
import type { ReactElement } from "react";
import { vi } from "vitest";

import { ShellActionsContext } from "@/components/shell/shell-actions";
import { TooltipProvider } from "@/components/ui/tooltip";
import { makeQueryClient } from "@/lib/api";

/** Query client without retries, so error paths resolve immediately. */
export function testClient() {
  const client = makeQueryClient();
  client.setDefaultOptions({ queries: { retry: false, staleTime: 0 } });
  return client;
}

export function renderApp(ui: ReactElement, { client = testClient(), createProject = vi.fn(), openPalette = vi.fn() } = {}) {
  const result = render(
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false} disableTransitionOnChange>
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <ShellActionsContext.Provider value={{ createProject, openPalette }}>{ui}</ShellActionsContext.Provider>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
  return { ...result, client, createProject, openPalette };
}

const V1 = "http://localhost:8000/v1";
export const api = (path: string) => `${V1}${path}`;

export const PROJECT_ID = "a3e1b2c4-d5f6-4a7b-8c9d-e0f1a2b3c4d5";
export const EMPTY_PROJECT_ID = "b4f2c3d5-e6a7-4b8c-9d0e-f1a2b3c4d5e6";
export const PLAN_ID = "c0d50567-abaa-43fd-ba84-0b9e05790fa7";

export function errorBody(code: string, message = "Server message") {
  return { error: { code, message, details: {} } };
}

// Adapted from src/lib/api/client.test.ts (P0-owned). Records each body, because MSW in Node can't parse jsdom's FormData.
/** Minimal fetch-backed XMLHttpRequest so the upload path runs through MSW in Node (reports one progress event). */
export class FetchXhr {
  static sent: FormData[] = [];
  status = 0;
  responseText = "";
  upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {};
  onload?: () => void;
  onerror?: () => void;
  onabort?: () => void;
  private method = "GET";
  private url = "";
  private headers: Record<string, string> = {};
  private responseHeaders = new Headers();
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v;
  }
  getResponseHeader(k: string) {
    return this.responseHeaders.get(k);
  }
  abort() {
    this.onabort?.();
  }
  send(body: FormData) {
    FetchXhr.sent.push(body);
    this.upload.onprogress?.({ lengthComputable: true, loaded: 1, total: 2 });
    fetch(this.url, { method: this.method, headers: this.headers, body }).then(
      async (r) => {
        this.status = r.status;
        this.responseHeaders = r.headers;
        this.responseText = await r.text();
        this.onload?.();
      },
      () => this.onerror?.(),
    );
  }
}


/** Radix and cmdk need these in jsdom. Call once per test file that opens a dialog, menu or palette. */
export function stubBrowserApis() {
  window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
  window.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  Element.prototype.scrollIntoView ??= () => {};
  vi.stubGlobal("XMLHttpRequest", FetchXhr);
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
}
