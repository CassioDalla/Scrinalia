import { Link } from "@tanstack/react-router";

import { EmptyState } from "@/components/ui/Feedback";
import { useCopy } from "@/i18n/context";

export function NotFoundRoute() {
  const copy = useCopy();

  return (
    <div className="px-6 py-10">
      <EmptyState
        title={copy.notFound.title}
        hint={copy.notFound.hint}
        action={
          <Link to="/" className="text-sm text-(--color-accent) hover:underline">
            {copy.notFound.backHome}
          </Link>
        }
      />
    </div>
  );
}
