import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { PageBody } from "@/components/layout/PageBody";
import { ACTION } from "@/lib/copy";
import { fill } from "@/i18n/maps";
import { formatCount, formatDateTime } from "@/lib/format";
import { useCopy } from "@/i18n/context";

/**
 * The infrastructure behind the workers: the database, the model server, the storage and the process.
 *
 * Each probe answers on its own — a database that is offline must not hide the fact that Ollama is
 * fine — so the screen renders four independent cards instead of one verdict. Nothing here writes,
 * and no secret value is ever shown: the process card reports that a secret exists, never what it is.
 */
export function SystemHealthRoute() {
  const messages = useCopy();
  const health = useQuery(queries.systemHealth());

  return (
    <>
      <PageHeader
        screen="health"
        actions={
          <Button size="sm" variant="secondary" onClick={() => void health.refetch()} disabled={health.isFetching}>
            {health.isFetching ? ACTION.recheck.pending : ACTION.recheck.label}
          </Button>
        }
      />

      <PageBody>
        {health.error ? <ErrorState error={health.error} /> : null}

        {health.isPending ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-40" />
            ))}
          </div>
        ) : null}

        {health.data ? (
          <>
            <p className="text-xs text-(--color-muted)">
              {fill(messages.pages.health.verified, { date: formatDateTime(health.data.generated_at) })}
            </p>

            <div className="grid gap-3 sm:grid-cols-2">
              <ProbeCard
                title={messages.pages.health.databaseTitle}
                ok={health.data.database.ok}
                detail={health.data.database.detail}
                lines={[
                  fill(messages.pages.health.documents, { count: formatCount(health.data.database.documents ?? 0) }),
                  fill(messages.pages.health.tags, { count: formatCount(health.data.database.tags ?? 0) }),
                  fill(messages.pages.health.entities, { count: formatCount(health.data.database.entities ?? 0) }),
                  fill(messages.pages.health.staging, {
                    count: formatCount(health.data.database.staging_records ?? 0),
                  }),
                ]}
              />

              <ProbeCard
                title={messages.pages.health.ollamaTitle}
                ok={health.data.ollama.ok}
                detail={health.data.ollama.detail}
                lines={[
                  fill(
                    health.data.ollama.host_source === "default"
                      ? messages.pages.health.addressDefault
                      : messages.pages.health.addressConfigured,
                    { host: health.data.ollama.host ?? "" },
                  ),
                  fill(messages.pages.health.installedModels, {
                    count: formatCount((health.data.ollama.installed_models ?? []).length),
                  }),
                  (health.data.ollama.required_models ?? []).length > 0
                    ? fill(messages.pages.health.requiredModels, {
                        list: (health.data.ollama.required_models ?? []).join(", "),
                      })
                    : messages.pages.health.noRequiredModels,
                ]}
              >
                {(health.data.ollama.missing_models ?? []).length > 0 ? (
                  <p className="text-xs text-(--color-danger)">
                    {fill(messages.pages.health.missingModels, {
                      list: (health.data.ollama.missing_models ?? []).join(", "),
                    })}
                  </p>
                ) : null}
              </ProbeCard>

              <ProbeCard
                title={messages.pages.health.storageTitle}
                ok={health.data.storage.ok}
                detail={health.data.storage.detail}
                lines={[
                  health.data.storage.configured
                    ? messages.pages.health.configured
                    : messages.pages.health.notConfigured,
                  health.data.storage.endpoint
                    ? fill(messages.pages.health.endpoint, { endpoint: health.data.storage.endpoint })
                    : messages.pages.health.noEndpoint,
                  health.data.storage.bucket
                    ? fill(messages.pages.health.bucket, { bucket: health.data.storage.bucket })
                    : messages.pages.health.noBucket,
                ]}
              />

              <ProbeCard
                title={messages.pages.health.originsTitle}
                ok={health.data.ingestion.ok}
                detail={health.data.ingestion.detail}
                lines={[
                  fill(messages.pages.health.originsActive, {
                    enabled: formatCount(health.data.ingestion.enabled ?? 0),
                    total: formatCount(health.data.ingestion.total ?? 0),
                  }),
                  (health.data.ingestion.origins ?? []).length > 0
                    ? (health.data.ingestion.origins ?? [])
                        .map(
                          (origin) =>
                            `${origin.label} (${
                              origin.enabled
                                ? messages.pages.health.originEnabled
                                : messages.pages.health.originPaused
                            })`,
                        )
                        .join(" · ")
                    : messages.pages.health.noOrigins,
                  messages.pages.health.originsNote,
                ]}
              >
                <Link to="/sistema/ingestao" className="text-xs font-medium text-(--color-accent) hover:underline">
                  {messages.pages.health.openOrigins}
                </Link>
              </ProbeCard>

              <ProbeCard
                title={messages.pages.health.configTitle}
                ok
                detail={null}
                lines={[
                  fill(messages.pages.health.logLine, {
                    level: health.data.process.log_level ?? "",
                    detailed: health.data.process.debug ? messages.pages.health.logDetailed : "",
                    dir: health.data.process.log_dir ?? "",
                  }),
                  fill(messages.pages.health.databaseLine, { path: health.data.process.database ?? "" }),
                  fill(messages.pages.health.ollamaLine, {
                    url: health.data.process.ollama_host_url ?? messages.pages.health.notConfigured,
                  }),
                  fill(messages.pages.health.storageLine, {
                    url: health.data.process.s3_endpoint_url ?? messages.pages.health.notConfigured,
                  }),
                  fill(messages.pages.health.scrapeLine, {
                    state: health.data.process.public_scrape_configured
                      ? messages.pages.health.defined
                      : messages.pages.health.notDefined,
                  }),
                  fill(messages.pages.health.secretsLine, {
                    list: Object.entries(health.data.process.secrets_present ?? {})
                      .map(
                        ([name, present]) =>
                          `${name} ${present ? messages.pages.health.yes : messages.pages.health.no}`,
                      )
                      .join(" · "),
                  }),
                ]}
              />
            </div>
          </>
        ) : null}
      </PageBody>
    </>
  );
}

function ProbeCard({
  title,
  ok,
  detail,
  lines,
  children,
}: {
  title: string;
  ok: boolean;
  detail?: string | null;
  lines: string[];
  children?: React.ReactNode;
}) {
  const messages = useCopy();
  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{title}</span>
        <Badge tone={ok ? "ok" : "danger"}>{ok ? messages.pages.health.responding : messages.pages.health.offline}</Badge>
      </CardHeader>
      <CardBody className="grid gap-1">
        {lines.map((line) => (
          <p key={line} className="text-xs text-(--color-muted)">
            {line}
          </p>
        ))}
        {detail ? <p className="text-xs text-(--color-danger)">{detail}</p> : null}
        {children}
      </CardBody>
    </Card>
  );
}
