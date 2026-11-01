"use client";

import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { ApiError } from "@/lib/api/client";

/** Same-origin path only: built from the router's own location, never from input. */
export const signInHref = (path: string) => `/sign-in?redirect_url=${encodeURIComponent(path)}`;

const isUnauthorized = (error: unknown) => error instanceof ApiError && error.status === 401;

/** The API client already retried with a fresh token, so a 401 here means the session is gone. */
export function AuthRedirect() {
  const qc = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const redirect = () => router.replace(signInHref(pathname + window.location.search));
    const unsubQueries = qc.getQueryCache().subscribe((e) => {
      if (e.type === "updated" && e.action.type === "error" && isUnauthorized(e.action.error)) redirect();
    });
    const unsubMutations = qc.getMutationCache().subscribe((e) => {
      if (e.type === "updated" && e.action.type === "error" && isUnauthorized(e.action.error)) redirect();
    });
    return () => {
      unsubQueries();
      unsubMutations();
    };
  }, [qc, router, pathname]);

  return null;
}
