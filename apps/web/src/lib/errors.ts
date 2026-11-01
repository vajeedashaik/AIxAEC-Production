import { ApiError } from "@/lib/api/client";

export interface ErrorCopy {
  title: string;
  description: string;
  /** Trying again could plausibly work without changing anything. */
  retryable: boolean;
}

const COPY: Record<string, Omit<ErrorCopy, "description"> & { description?: string }> = {
  unauthorized: { title: "Your session ended", description: "Sign in again to continue.", retryable: false },
  forbidden: { title: "You don't have access", description: "This account can't do that.", retryable: false },
  not_found: { title: "Not found", description: "It may have been deleted, or it belongs to another account.", retryable: false },
  validation_error: { title: "That wasn't valid", retryable: false },
  conflict: { title: "That conflicts with the current state", retryable: true },
  stale_model: { title: "The plan changed", description: "Refresh to see the latest version.", retryable: true },
  model_not_ready: { title: "The model isn't ready", description: "This plan is still being processed.", retryable: true },
  already_processing: { title: "Already in the queue", description: "This plan is already being processed.", retryable: false },
  quota_exceeded: { title: "Quota reached", description: "Delete a project or floor plan to make room.", retryable: false },
  payload_too_large: { title: "File too large", description: "Upload a file of 25 MB or less.", retryable: false },
  unsupported_media_type: { title: "Unsupported file", description: "Upload a PNG, JPG or PDF.", retryable: false },
  rate_limited: { title: "Too many requests", description: "Wait a moment, then try again.", retryable: true },
  upstream_unavailable: { title: "Service unavailable", description: "A service we depend on isn't responding. Try again shortly.", retryable: true },
  network_error: { title: "Can't reach the server", description: "Check your connection and try again.", retryable: true },
  internal_error: { title: "Something went wrong on our side", description: "Try again. If it keeps happening, the problem is ours.", retryable: true },
};

/** Maps any thrown value to copy for a toast or ErrorState. API messages are shown only where the API wrote them for people. */
export function describeError(error: unknown): ErrorCopy {
  if (error instanceof ApiError) {
    const copy = COPY[error.code] ?? COPY.internal_error;
    const wait = error.code === "rate_limited" && error.retryAfter ? `Try again in ${Math.ceil(error.retryAfter)} s.` : undefined;
    return { title: copy.title, description: wait ?? copy.description ?? error.message, retryable: copy.retryable };
  }
  // fetch() rejects with a TypeError when the server can't be reached.
  if (error instanceof TypeError) return { ...COPY.network_error, description: COPY.network_error.description! };
  return { ...COPY.internal_error, description: COPY.internal_error.description! };
}
