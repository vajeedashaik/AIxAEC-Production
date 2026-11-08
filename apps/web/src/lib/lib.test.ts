import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/client";

import { describeError } from "./errors";
import { fileKind, formatBytes, formatDuration } from "./format";
import { setPreference } from "./preferences";

describe("describeError", () => {
  it.each([
    ["unauthorized", 401, "Your session ended"],
    ["not_found", 404, "Not found"],
    ["payload_too_large", 413, "File too large"],
    ["unsupported_media_type", 415, "Unsupported file"],
    ["quota_exceeded", 409, "Quota reached"],
    ["upstream_unavailable", 503, "Service unavailable"],
  ])("maps %s to its own copy", (code, status, title) => {
    expect(describeError(new ApiError(status, code, "raw server text")).title).toBe(title);
  });

  it("shows the API's message for validation errors, since it names the field", () => {
    expect(describeError(new ApiError(422, "validation_error", "Name is required.")).description).toBe("Name is required.");
  });

  it("states the wait from Retry-After on a rate limit", () => {
    expect(describeError(new ApiError(429, "rate_limited", "x", {}, 12.2)).description).toBe("Try again in 13 s.");
  });

  it("marks transient errors retryable and final ones not", () => {
    expect(describeError(new ApiError(500, "internal_error", "x")).retryable).toBe(true);
    expect(describeError(new ApiError(404, "not_found", "x")).retryable).toBe(false);
  });

  it("falls back to generic copy for unknown codes, without echoing the server's text", () => {
    const copy = describeError(new ApiError(500, "weird_code", "stack trace here"));
    expect(copy.title).toBe("Something went wrong on our side");
    expect(copy.description).not.toContain("stack trace");
  });

  it("treats a fetch TypeError as a network problem", () => {
    expect(describeError(new TypeError("Failed to fetch")).title).toBe("Can't reach the server");
  });
});

describe("format", () => {
  it("formats bytes with binary units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(48213)).toBe("47.1 KB");
    expect(formatBytes(25 * 1024 * 1024)).toBe("25.0 MB");
  });

  it("formats durations", () => {
    expect(formatDuration(340)).toBe("340 ms");
    expect(formatDuration(1240)).toBe("1.2 s");
  });

  it("names file kinds", () => {
    expect(fileKind("image/jpeg")).toBe("JPG");
    expect(fileKind("application/pdf")).toBe("PDF");
  });
});

describe("density preference", () => {
  it("stores the choice and toggles the class P6 honours", () => {
    setPreference("density", "compact");
    expect(localStorage.getItem("aec.density")).toBe("compact");
    expect(document.documentElement).toHaveClass("density-compact");
    setPreference("density", "comfortable");
    expect(document.documentElement).not.toHaveClass("density-compact");
  });
});

describe("describeError for oversized uploads", () => {
  it("blames pixels, not megabytes, when the API says the image has too many", () => {
    const pixels = describeError(new ApiError(413, "payload_too_large", "The image has too many pixels."));
    const bytes = describeError(new ApiError(413, "payload_too_large", "The file is too large."));
    expect(pixels.description).toMatch(/too many pixels/);
    expect(bytes.description).toBe("Upload a file of 25 MB or less.");
  });
});
