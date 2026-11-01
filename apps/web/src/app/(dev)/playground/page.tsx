import { notFound } from "next/navigation";

import { Placeholder } from "@/components/placeholder";

/** P6 component playground: fixture models, no auth. Never served in production. */
export default function PlaygroundPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <Placeholder title="Workspace playground" owner="P6" />;
}
