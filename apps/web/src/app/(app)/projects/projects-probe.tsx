"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { queryKeys, useApi } from "@/lib/api";

/** P0 wiring check: lists projects through the typed client (MSW in mock mode). */
export function ProjectsProbe() {
  const api = useApi();
  const { data, error, isPending } = useQuery({ queryKey: queryKeys.projects.list(), queryFn: ({ signal }) => api.listProjects({}, signal) });
  if (isPending) return <p>Loading projects…</p>;
  if (error) return <p role="alert">Could not load projects: {error.message}</p>;
  return (
    <ul className="mt-4 flex flex-col gap-1">
      {data.items.map((p) => (
        <li key={p.id}>
          <Link className="text-foreground underline-offset-4 hover:underline" href={`/projects/${p.id}`}>
            {p.name}
          </Link>{" "}
          <span className="numeric text-micro">{p.floorplan_count} plans</span>
        </li>
      ))}
    </ul>
  );
}
