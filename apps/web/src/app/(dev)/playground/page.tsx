import { notFound } from "next/navigation";

import { Playground } from "./playground";

/** P6 component playground: fixture models, no auth. Never served in production. */
export default function PlaygroundPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <Playground />;
}
