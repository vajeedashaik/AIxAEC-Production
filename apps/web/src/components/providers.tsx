"use client";

import { ThemeProvider } from "next-themes";
import type { ReactNode } from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ClerkTokenBridge, QueryProvider } from "@/lib/api/query";
import { CLERK_ENABLED } from "@/lib/clerk";
import { MockProvider } from "@/mocks/MockProvider";

export function Providers({ children }: { children: ReactNode }) {
  const app = (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <MockProvider>
        <QueryProvider>
          <TooltipProvider delayDuration={300}>
            {children}
            <Toaster />
          </TooltipProvider>
        </QueryProvider>
      </MockProvider>
    </ThemeProvider>
  );
  return CLERK_ENABLED ? <ClerkTokenBridge>{app}</ClerkTokenBridge> : app;
}
