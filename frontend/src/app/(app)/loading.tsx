import { WorkspaceSkeleton } from "@/components/ui/skeleton";

export default function AuthenticatedLoading() {
  return (
    <div className="px-0 py-2">
      <WorkspaceSkeleton />
    </div>
  );
}
