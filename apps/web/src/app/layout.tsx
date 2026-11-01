import { ClerkProvider } from "@clerk/nextjs";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { CLERK_ENABLED } from "@/lib/clerk";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "AEC Studio", template: "%s · AEC Studio" },
  description: "Turn a floor plan into a structured, editable building model.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const page = (
    <html lang="en" suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable} h-full`}>
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
  return CLERK_ENABLED ? <ClerkProvider>{page}</ClerkProvider> : page;
}
