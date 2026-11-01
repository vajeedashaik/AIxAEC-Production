"use client";

import { UserButton } from "@clerk/nextjs";
import { FolderIcon, LayoutDashboardIcon, MenuIcon, PanelLeftCloseIcon, PanelLeftOpenIcon, SearchIcon, SettingsIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ICON_STROKE, Kbd } from "@/components/composites";
import { Logo, LogoMark } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useProjects } from "@/features/projects/hooks";
import { CreateProjectDialog } from "@/features/projects/project-form-dialog";
import { CLERK_ENABLED } from "@/lib/clerk";
import { clerkAppearance } from "@/lib/clerk-appearance";
import { usePreference } from "@/lib/preferences";
import { cn } from "@/lib/utils";

import { AuthRedirect } from "./auth-redirect";
import { Breadcrumbs } from "./breadcrumbs";
import { CommandPalette } from "./command-palette";
import { ShellActionsContext } from "./shell-actions";
import { ThemeToggle } from "./theme-toggle";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboardIcon },
  { href: "/projects", label: "Projects", icon: FolderIcon },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

const isActive = (pathname: string, href: string) => pathname === href || pathname.startsWith(`${href}/`);
const WORKSPACE_ROUTE = /^\/projects\/[^/]+\/floorplans\//;

const itemClass = (active: boolean) =>
  cn(
    "flex h-(--control-h-md) items-center gap-2 rounded-md px-2 text-ui transition-colors duration-(--duration-instant) hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
    active ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "text-sidebar-foreground",
  );

function SidebarNav({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const { data } = useProjects(1, 100);
  const recent = useMemo(() => [...(data?.items ?? [])].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, 5), [data]);

  return (
    <>
      <nav aria-label="Main" className="flex flex-col gap-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          const link = (
            <Link href={href} aria-current={active ? "page" : undefined} aria-label={collapsed ? label : undefined} onClick={onNavigate} className={cn(itemClass(active), collapsed && "justify-center px-0")}>
              <Icon className="size-4 shrink-0" strokeWidth={ICON_STROKE} aria-hidden />
              {!collapsed && label}
            </Link>
          );
          return collapsed ? (
            <Tooltip key={href}>
              <TooltipTrigger asChild>{link}</TooltipTrigger>
              <TooltipContent side="right">{label}</TooltipContent>
            </Tooltip>
          ) : (
            <span key={href} className="contents">
              {link}
            </span>
          );
        })}
      </nav>
      {!collapsed && recent.length > 0 && (
        <nav aria-labelledby="recent-projects" className="mt-6 flex min-h-0 flex-col gap-0.5">
          <h2 id="recent-projects" className="px-2 pb-1 text-micro text-muted-foreground">
            Recent projects
          </h2>
          {recent.map((p) => {
            const href = `/projects/${p.id}`;
            const active = isActive(pathname, href);
            return (
              <Link key={p.id} href={href} aria-current={active ? "page" : undefined} onClick={onNavigate} className={itemClass(active)}>
                <span className="truncate">{p.name}</span>
              </Link>
            );
          })}
        </nav>
      )}
    </>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [sidebar, setSidebar] = usePreference("sidebar");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  // The workspace canvas takes every remaining pixel (DESIGN §6), so the rail stays closed there.
  const inWorkspace = WORKSPACE_ROUTE.test(pathname);
  const collapsed = inWorkspace || sidebar === "collapsed";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const actions = useMemo(() => ({ createProject: () => setCreateOpen(true), openPalette: () => setPaletteOpen(true) }), []);

  return (
    <ShellActionsContext.Provider value={actions}>
      <AuthRedirect />
      <a href="#main" className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:absolute focus:top-2 focus:left-2">
        Skip to content
      </a>
      <div className="flex h-dvh overflow-hidden">
        <aside aria-label="Sidebar" className={cn("flex shrink-0 flex-col border-r bg-sidebar p-2 max-md:hidden", collapsed ? "w-12" : "w-(--sidebar-w)")}>
          <Link href="/dashboard" aria-label="AEC Studio, go to dashboard" className={cn("mb-3 flex h-(--control-h-md) items-center rounded-md", collapsed ? "justify-center" : "px-2")}>
            {collapsed ? <LogoMark /> : <Logo />}
          </Link>
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
            <SidebarNav collapsed={collapsed} />
          </div>
          {!inWorkspace && (
            <Button variant="ghost" size="icon" className={cn("mt-2 text-muted-foreground", !collapsed && "self-end")} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} onClick={() => setSidebar(collapsed ? "expanded" : "collapsed")}>
              {collapsed ? <PanelLeftOpenIcon strokeWidth={ICON_STROKE} /> : <PanelLeftCloseIcon strokeWidth={ICON_STROKE} />}
            </Button>
          )}
        </aside>

        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side="left" className="w-64 bg-sidebar p-2">
            <SheetHeader className="p-2">
              <SheetTitle>
                <Logo />
              </SheetTitle>
              <SheetDescription className="sr-only">Main navigation</SheetDescription>
            </SheetHeader>
            <SidebarNav collapsed={false} onNavigate={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-(--topbar-h) shrink-0 items-center gap-2 border-b bg-background px-2 md:px-4">
            <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open navigation" onClick={() => setMobileOpen(true)}>
              <MenuIcon strokeWidth={ICON_STROKE} />
            </Button>
            <Breadcrumbs />
            <div className="ml-auto flex shrink-0 items-center gap-1">
              <Button variant="outline" className="w-56 justify-start gap-2 px-2 font-normal text-muted-foreground max-lg:size-(--control-h-md) max-lg:justify-center max-lg:px-0" aria-label="Open command palette" onClick={() => setPaletteOpen(true)}>
                <SearchIcon strokeWidth={ICON_STROKE} />
                <span className="max-lg:hidden">Jump to…</span>
                <Kbd className="ml-auto max-lg:hidden">Ctrl K</Kbd>
              </Button>
              <ThemeToggle />
              {CLERK_ENABLED && (
                <span className="ml-1 grid size-7 place-items-center">
                  <UserButton appearance={clerkAppearance} />
                </span>
              )}
            </div>
          </header>
          <main id="main" tabIndex={-1} className="flex min-h-0 flex-1 flex-col overflow-y-auto outline-none">
            {children}
          </main>
        </div>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} onCreateProject={actions.createProject} />
      <CreateProjectDialog open={createOpen} onOpenChange={setCreateOpen} />
    </ShellActionsContext.Provider>
  );
}
