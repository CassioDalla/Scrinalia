import { useQuery } from "@tanstack/react-query";

import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
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
        title="Diagnóstico"
        subtitle="Banco, modelos do Ollama, storage de miniaturas e a configuração efetiva do processo."
        actions={
          <Button size="sm" variant="secondary" onClick={() => void health.refetch()} disabled={health.isFetching}>
            {health.isFetching ? "Verificando…" : "Verificar de novo"}
          </Button>
        }
      />

      <div className="grid max-w-5xl gap-4 px-6 py-5">
        {health.error ? <ErrorState error={health.error} /> : null}

        {health.isPending ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-40" />
            ))}
          </div>
        ) : null}

        {health.data ? (
          <>
            <p className="text-xs text-(--color-muted)">
              Leitura de {formatDateTime(health.data.generated_at)}. Cada verificação tem um limite de tempo próprio,
              então um serviço fora do ar aparece como um cartão vermelho, não como uma tela quebrada.
            </p>

            <div className="grid gap-3 sm:grid-cols-2">
              <ProbeCard
                title="Banco de dados"
                ok={health.data.database.ok}
                detail={health.data.database.detail}
                lines={[
                  `${formatCount(health.data.database.documents ?? 0)} descrições`,
                  `${formatCount(health.data.database.tags ?? 0)} tags`,
                  `${formatCount(health.data.database.entities ?? 0)} entidades`,
                  `${formatCount(health.data.database.staging_records ?? 0)} registros de staging`,
                ]}
              />

              <ProbeCard
                title="Ollama (modelos)"
                ok={health.data.ollama.ok}
                detail={health.data.ollama.detail}
                lines={[
                  `host ${health.data.ollama.host} (${health.data.ollama.host_source === "default" ? "padrão local" : "OLLAMA_HOST_URL"})`,
                  `${formatCount((health.data.ollama.installed_models ?? []).length)} modelo(s) instalado(s)`,
                  (health.data.ollama.required_models ?? []).length > 0
                    ? `presets exigem: ${(health.data.ollama.required_models ?? []).join(", ")}`
                    : "nenhum preset exige modelo",
                ]}
              >
                {(health.data.ollama.missing_models ?? []).length > 0 ? (
                  <p className="text-xs text-(--color-danger)">
                    Faltam no servidor: {(health.data.ollama.missing_models ?? []).join(", ")}. Uma execução que use esse preset
                    falha ao carregar o modelo.
                  </p>
                ) : null}
              </ProbeCard>

              <ProbeCard
                title="Storage das miniaturas"
                ok={health.data.storage.ok}
                detail={health.data.storage.detail}
                lines={[
                  health.data.storage.configured ? "configurado" : "não configurado",
                  health.data.storage.endpoint ? `endpoint ${health.data.storage.endpoint}` : "sem endpoint",
                  health.data.storage.bucket ? `bucket ${health.data.storage.bucket}` : "sem bucket",
                ]}
              />

              <ProbeCard
                title="Processo da API"
                ok
                detail={null}
                lines={[
                  `log ${health.data.process.log_level}${health.data.process.debug ? " · debug ligado" : ""} em ${health.data.process.log_dir}`,
                  `banco ${health.data.process.database}`,
                  `ollama ${health.data.process.ollama_host_url ?? "não configurado"}`,
                  `s3 ${health.data.process.s3_endpoint_url ?? "não configurado"}`,
                  `ArqDoc ${health.data.process.arqdoc_configured ? "configurado" : "não configurado"} · site público ${
                    health.data.process.public_scrape_configured ? "configurado" : "não configurado"
                  }`,
                  `segredos presentes: ${Object.entries(health.data.process.secrets_present ?? {})
                    .map(([name, present]) => `${name} ${present ? "sim" : "não"}`)
                    .join(" · ")}`,
                ]}
              />
            </div>
          </>
        ) : null}
      </div>
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
