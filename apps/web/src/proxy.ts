import { clerkMiddleware } from "@clerk/nextjs/server";
import { NextResponse, type NextFetchEvent, type NextRequest } from "next/server";

// The (app) route group: route groups don't appear in URLs, so list its top-level paths.
// The API is the real security boundary (owner-scoped, verifies every token); this is the UX redirect.
const APP_ROUTE = /^\/(dashboard|projects|settings)(\/|$)/;

const isDev = process.env.NODE_ENV !== "production";
// Dev-only: let P5/P6 work offline against MSW without a Clerk session.
const mockBypass = isDev && process.env.NEXT_PUBLIC_API_MOCKING === "on";
// Dev without Clerk keys: skip auth entirely (see src/lib/clerk.ts). Production without keys falls through to
// clerkMiddleware, which throws (fail closed).
const clerkOff = isDev && !(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY && process.env.CLERK_SECRET_KEY);

const clerk = clerkMiddleware(async (auth, request) => {
  if (APP_ROUTE.test(request.nextUrl.pathname) && !mockBypass) await auth.protect();
});

export default function proxy(request: NextRequest, event: NextFetchEvent) {
  return clerkOff ? NextResponse.next() : clerk(request, event);
}

export const config = {
  matcher: [
    // Skip Next.js internals and static files, unless found in search params
    "/((?!_next|mockServiceWorker\\.js|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
