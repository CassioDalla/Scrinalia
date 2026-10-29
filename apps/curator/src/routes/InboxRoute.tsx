import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { queries } from "@/api/queries";
import type { CurationQueue } from "@/api/client";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { PageBody } from "@/components/layout/PageBody";
import { formatCount, formatDateTime } from "@/lib/format";
import { QUEUE_COPY, QUEUE_DESTINATIONS } from "@/lib/queues";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";

function QueueCard({ queue }: { queue: CurationQueue }) {
  const destination = QUEUE_DESTINATIONS[queue.key];
  const empty = queue.count === 0;
  const copy = QUEUE_COPY[queue.key];
  const messages = useCopy();

  const body = (
    <CardBody className="flex h-full flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <span className={empty ? "text-sm font-medium text-(--color-muted)" : "text-sm font-medium"}>
          {copy.label}
        </span>
        <span
          className={
            empty
              ? "text-2xl leading-none font-semibold tabular-nums text-(--color-muted)/50"
              : "text-2xl leading-none font-semibold tabular-nums"
          }
        >
          {formatCount(queue.count)}
        </span>
      </div>
      <p className="text-xs text-(--color-muted)">{copy.description}</p>
      <div className="mt-auto pt-1">
        {empty ? (
          // Zero is not hidden: the archivist has to know the queue exists and is empty.
          <Badge tone="neutral">{messages.pages.inbox.empty}</Badge>
        ) : (
          <span className="text-xs font-medium text-(--color-accent)">{messages.pages.inbox.open}</span>
        )}
      </div>
    </CardBody>
  );

  const className = "h-full transition " + (empty ? "opacity-60" : "");

  return (
    <Link {...destination} className={className + " hover:ring-(--color-accent)/40"}>
      <Card className="h-full hover:ring-(--color-accent)/40">{body}</Card>
    </Link>
  );
}

export function InboxRoute() {
  const messages = useCopy();
  const { data, isPending, error } = useQuery(queries.inbox());

  return (
    <>
      <PageHeader screen="inbox" />
      <PageBody>
        {error ? <ErrorState error={error} /> : null}

        {isPending ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-32" />
            ))}
          </div>
        ) : null}

        {data && data.queues && data.queues.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.queues.map((queue) => (
              <QueueCard key={queue.key} queue={queue} />
            ))}
          </div>
        ) : null}

        {data && (!data.queues || data.queues.length === 0) ? (
          <EmptyState
            title={messages.pages.inbox.emptyTitle}
            hint={messages.pages.inbox.emptyHint}
          />
        ) : null}

        {data ? (
          <p className="mt-4 text-xs text-(--color-muted)">
            {fill(messages.pages.inbox.countsGenerated, { date: formatDateTime(data.generated_at) })}
          </p>
        ) : null}
      </PageBody>
    </>
  );
}
