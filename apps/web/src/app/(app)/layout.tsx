import { UserButton } from "@clerk/nextjs";
import Link from "next/link";

import { CLERK_ENABLED } from "@/lib/clerk";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/projects", label: "Projects" },
  { href: "/settings", label: "Settings" },
];

/** P0 app shell placeholder (P5 owns the real shell). */
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-(--topbar-h) items-center gap-6 border-b bg-card px-4">
        <Link href="/dashboard" className="font-semibold tracking-tight">
          AEC Studio
        </Link>
        <nav aria-label="Main" className="flex gap-4 text-muted-foreground">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} className="hover:text-foreground">
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto">
          {CLERK_ENABLED && <UserButton />}
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}
