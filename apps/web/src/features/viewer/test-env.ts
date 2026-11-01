// jsdom gaps that Radix and the resizable panels need. Import from tests only.
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

export function installDomStubs() {
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
}

afterEach(() => cleanup());
