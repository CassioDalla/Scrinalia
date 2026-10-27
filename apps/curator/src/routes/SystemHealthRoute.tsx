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
import { formatCount, formatDateTime } from "@/lib/format";

/**
 * The infrastructure behind the workers: the database, the model server, the storage and the process.
 *
 * Each probe answers on its own — a database that is offline must not hide the fact that Ollama is
 * fine — so the screen renders four independent cards instead of one verdict. Nothing here writes,
 * and no secret value is ever shown: the process card reports that a secret exists, never what it is.
 */
export function SystemHealthRoute() {
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
              Verificado em {formatDateTime(health.data.generated_at)}. Cada verificação tem seu próprio limite de
              tempo: um serviço fora do ar aparece como um cartão vermelho, não como uma tela quebrada.
            </p>

            <div className="grid gap-3 sm:grid-cols-2">
              <ProbeCard
                title="Acervo"
                ok={health.data.database.ok}
                detail={health.data.database.detail}
                lines={[
                  `${formatCount(health.data.database.documents ?? 0)} descrições`,
                  `${formatCount(health.data.database.tags ?? 0)} tags`,
                  `${formatCount(health.data.database.entities ?? 0)} entidades`,
                  `${formatCount(health.data.database.staging_records ?? 0)} registros aguardando transferência`,
                ]}
              />

              <ProbeCard
                title="Modelos (Ollama)"
                ok={health.data.ollama.ok}
                detail={health.data.ollama.detail}
                lines={[
                  `endereço ${health.data.ollama.host} (${health.data.ollama.host_source === "default" ? "padrão local" : "definido na configuração"})`,
                  `modelos instalados: ${formatCount((health.data.ollama.installed_models ?? []).length)}`,
                  (health.data.ollama.required_models ?? []).length > 0
                    ? `modelos necessários: ${(health.data.ollama.required_models ?? []).join(", ")}`
                    : "nenhum modelo é necessário",
                ]}
              >
                {(health.data.ollama.missing_models ?? []).length > 0 ? (
                  <p className="text-xs text-(--color-danger)">
                    Faltam no servidor: {(health.data.ollama.missing_models ?? []).join(", ")}. Uma execução que
                    precise de um deles falha ao carregar o modelo.
                  </p>
                ) : null}
              </ProbeCard>

              <ProbeCard
                title="Armazenamento das miniaturas"
                ok={health.data.storage.ok}
                detail={health.data.storage.detail}
                lines={[
                  health.data.storage.configured ? "configurado" : "não configurado",
                  health.data.storage.endpoint ? `endereço ${health.data.storage.endpoint}` : "sem endereço",
                  health.data.storage.bucket
                    ? `espaço de armazenamento ${health.data.storage.bucket}`
                    : "sem espaço de armazenamento",
                ]}
              />

              <ProbeCard
                title="Origens"
                ok={health.data.ingestion.ok}
                detail={health.data.ingestion.detail}
                lines={[
                  `${formatCount(health.data.ingestion.enabled ?? 0)} de ${formatCount(health.data.ingestion.total ?? 0)} origens ativas`,
                  (health.data.ingestion.origins ?? []).length > 0
                    ? (health.data.ingestion.origins ?? [])
                        .map((origin) => `${origin.label} (${origin.enabled ? "ativa" : "pausada"})`)
                        .join(" · ")
                    : "nenhuma origem configurada",
                  "a fila, a agenda e a configuração de cada origem ficam na tela de origens",
                ]}
              >
                <Link to="/sistema/ingestao" className="text-xs font-medium text-(--color-accent) hover:underline">
                  Abrir origens
                </Link>
              </ProbeCard>

              <ProbeCard
                title="Configuração em uso"
                ok
                detail={null}
                lines={[
                  `registros ${health.data.process.log_level}${health.data.process.debug ? " · modo detalhado" : ""} em ${health.data.process.log_dir}`,
                  `acervo em ${health.data.process.database}`,
                  `modelos em ${health.data.process.ollama_host_url ?? "não configurado"}`,
                  `armazenamento em ${health.data.process.s3_endpoint_url ?? "não configurado"}`,
                  `endereço padrão das origens: ${
                    health.data.process.public_scrape_configured ? "definido" : "não definido"
                  }`,
                  `chaves e senhas configuradas: ${Object.entries(health.data.process.secrets_present ?? {})
                    .map(([name, present]) => `${name} ${present ? "sim" : "não"}`)
                    .join(" · ")}`,
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
  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{title}</span>
        <Badge tone={ok ? "ok" : "danger"}>{ok ? "respondendo" : "fora do ar"}</Badge>
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
