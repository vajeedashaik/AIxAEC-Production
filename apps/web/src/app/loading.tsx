import { SkeletonList } from "@/components/composites";

export default function Loading() {
  return <SkeletonList rows={4} label="Loading page" className="mx-auto w-full max-w-6xl p-6" />;
}
