import { ClerkProvider } from "@clerk/nextjs";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { CLERK_ENABLED } from "@/lib/clerk";
import { clerkAppearance } from "@/lib/clerk-appearance";
import { DENSITY_BOOT_SCRIPT } from "@/lib/density";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "AEC Studio", template: "%s · AEC Studio" },
  description: "Upload a floor plan, get a typed building model, and edit it by text or voice. A deterministic geometry engine applies every change as a new version.",
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const page = (
    <html lang="en" suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable} h-full`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: DENSITY_BOOT_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
  return CLERK_ENABLED ? <ClerkProvider appearance={clerkAppearance}>{page}</ClerkProvider> : page;
}
