"use client";

import { useAuth } from "@clerk/nextjs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { ApiError, createApiClient, type ApiClient, type GetToken } from "./client";

export const queryKeys = {
  me: ["me"] as const,
  projects: {
    all: ["projects"] as const,
    list: (params: { limit?: number; offset?: number } = {}) => ["projects", "list", params] as const,
    detail: (projectId: string) => ["projects", "detail", projectId] as const,
    floorplans: (projectId: string) => ["projects", "detail", projectId, "floorplans"] as const,
  },
  floorplans: {
    detail: (floorplanId: string) => ["floorplans", floorplanId] as const,
    job: (floorplanId: string) => ["floorplans", floorplanId, "job"] as const,
    model: (floorplanId: string, version?: number) => ["floorplans", floorplanId, "model", version ?? "head"] as const,
    artifacts: (floorplanId: string) => ["floorplans", floorplanId, "artifacts"] as const,
    history: (floorplanId: string) => ["floorplans", floorplanId, "history"] as const,
  },
};

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        // Client errors are final; retry network/5xx twice.
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
      },
    },
  });
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(makeQueryClient);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const noToken: GetToken = async () => null;
const GetTokenContext = createContext<GetToken>(noToken);

/** Supplies the Clerk session token to useApi(). Render inside <ClerkProvider>. */
export function ClerkTokenBridge({ children }: { children: ReactNode }) {
  const { getToken } = useAuth();
  const value = useMemo<GetToken>(() => (o) => getToken(o), [getToken]);
  return <GetTokenContext.Provider value={value}>{children}</GetTokenContext.Provider>;
}

/** The API client bound to the signed-in Clerk session (no token when Clerk isn't configured). */
export function useApi(): ApiClient {
  const getToken = useContext(GetTokenContext);
  return useMemo(() => createApiClient({ getToken }), [getToken]);
}
