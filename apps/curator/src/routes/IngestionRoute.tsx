import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import {
  createManualIngestion,
  deleteIngestionSchedule,
  fetchCurrentUser,
  importCsv,
  saveIngestionSchedule,
  triggerIngestionRun,
  updateIngestionOrigin,
  type CsvRowStatus,
  type IngestionOption,
  type IngestionOrigin,
  type OriginConfigField,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageBody } from "@/components/layout/PageBody";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { CsvParseError, decodeCsv, detectDelimiter, parseCsv, type CsvDelimiter } from "@/lib/csv";
import { buildTemplate, mapCsv, toRequestBody, type CsvMapping } from "@/lib/csvImport";
import { can } from "@/lib/permissions";
import { formatCount, formatDateTime } from "@/lib/format";
import { routeMessage } from "@/lib/messages";
import { RUN_STATUS_LABEL, RUN_STATUS_TONE } from "@/lib/system";

/**
 * Ingestão: the stage in front of the archive, origin by origin.
 *
 * Two questions share this screen because they share the object. The origin cards answer *which queue
 * is this, what does it read and when does it run* — the operator's question, and the axis #44 added
 * to a panel that used to start at `transfer`. The manual form answers *how does an archivist type a
 * record*, and its answer is deliberately the same pipeline: raw -> staging -> transfer -> AI. The
 * submit is not an approval; the archive description is born `PENDING_AI` and the review happens in
 * the dossier after the AI runs.
 */
export function IngestionRoute() {
  const { data, isPending, error } = useQuery({
    ...queries.ingestionOrigins(),
    // A queued run changes when a runner appears; a running one changes every few seconds.
    refetchInterval: (query) =>
      (query.state.data?.origins ?? []).some((origin) => origin.active_run_id != null) ? 5_000 : 15_000,
  });
  const current = useQuery({ queryKey: ["current-user"], queryFn: fetchCurrentUser, retry: false });
  const role = current.data?.role ?? "VIEWER";
  const canOperate = can(role, "OPERATE");
  const canCurate = can(role, "CURATE");

  return (
    <>
      <PageHeader screen="ingestion" />
      <PageBody className="gap-3">
        {error ? <ErrorState error={error} /> : null}

        <Card>
          <CardBody className="grid gap-2">
            <p className="text-sm text-(--color-muted)">
              A ingestão lê a origem para o <span className="font-mono text-xs">raw</span>, estrutura o
              resultado no <span className="font-mono text-xs">staging</span> e o deixa pronto para a
              transferência. A origem tem a sua própria fila, a sua própria agenda e a sua própria
              configuração; a IA e o painel de workers vêm depois.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Link to="/sistema/workers">
                <Button size="sm" variant="secondary">
                  Workers de IA
                </Button>
              </Link>
              <Link to="/sistema/execucoes">
                <Button size="sm" variant="ghost">
                  Execuções
                </Button>
              </Link>
            </div>
          </CardBody>
        </Card>

        {canCurate ? <ManualEntryCard /> : null}

        {canCurate ? <CsvImportCard /> : null}

        {isPending ? (
          <div className="grid gap-3">
            {Array.from({ length: 2 }).map((_, index) => (
              <Skeleton key={index} className="h-32" />
            ))}
          </div>
        ) : null}

        {(data?.origins ?? []).map((origin) => (
          <OriginCard key={origin.code} origin={origin} canOperate={canOperate} />
        ))}
      </PageBody>
    </>
  );
}

function ManualEntryCard() {
  const queryClient = useQueryClient();
  const [descriptionId, setDescriptionId] = useState(() => `manual-${crypto.randomUUID()}`);
  const [title, setTitle] = useState("");
  const [referenceCode, setReferenceCode] = useState("");
  const [level, setLevel] = useState("");
  const [documentDate, setDocumentDate] = useState("");
  const [scopeContent, setScopeContent] = useState("");
  const [producers, setProducers] = useState("");
  const [bioHistory, setBioHistory] = useState("");
  const [accessConditions, setAccessConditions] = useState("");
  const [indexingPoints, setIndexingPoints] = useState("");

  const submit = useMutation({
    mutationFn: () =>
      createManualIngestion({
        description_id: descriptionId,
        title: title.trim(),
        reference_code: emptyToNull(referenceCode),
        level: emptyToNull(level),
        document_date: emptyToNull(documentDate),
        scope_content: emptyToNull(scopeContent),
        producers: emptyToNull(producers),
        admin_bio_history: emptyToNull(bioHistory),
        access_conditions: emptyToNull(accessConditions),
        indexing_points: emptyToNull(indexingPoints),
      }),
    onSuccess: () => {
      // The origin's pending count and the ledger both moved: the record is staged and a transfer
      // may have been queued.
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
      void queryClient.invalidateQueries({ queryKey: ["system", "runs"] });
      setDescriptionId(`manual-${crypto.randomUUID()}`);
    },
  });

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-2 text-sm font-semibold">
        <span>Entrada manual</span>
        <Badge tone="accent">PENDING_AI</Badge>
      </CardHeader>
      <CardBody className="grid gap-3">
        <p className="text-xs text-(--color-muted)">
          A descrição digitada aqui <strong>não é uma aprovação</strong>. Ela entra no mesmo staging e na
          mesma fila de IA das demais origens; depois da IA, o dossiê é o lugar de revisar e aprovar.
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Título">
            <Input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={500} />
          </Field>
          <Field label="Código de referência">
            <Input value={referenceCode} onChange={(event) => setReferenceCode(event.target.value)} />
          </Field>
          <Field label="Nível de descrição">
            <Input value={level} onChange={(event) => setLevel(event.target.value)} placeholder="Ex.: Série" />
          </Field>
          <Field label="Data de produção">
            <Input type="date" value={documentDate} onChange={(event) => setDocumentDate(event.target.value)} />
          </Field>
          <Field label="Produtores">
            <Input value={producers} onChange={(event) => setProducers(event.target.value)} />
          </Field>
          <Field label="Condições de acesso">
            <Input value={accessConditions} onChange={(event) => setAccessConditions(event.target.value)} />
          </Field>
        </div>

        <Field label="Âmbito e conteúdo">
          <Textarea value={scopeContent} onChange={(event) => setScopeContent(event.target.value)} rows={3} />
        </Field>
        <Field label="História administrativa / biográfica">
          <Textarea value={bioHistory} onChange={(event) => setBioHistory(event.target.value)} rows={2} />
        </Field>
        <Field label="Pontos de acesso">
          <Input
            value={indexingPoints}
            onChange={(event) => setIndexingPoints(event.target.value)}
            placeholder="separados por vírgula"
          />
        </Field>

        {submit.data ? (
          <Notice tone="ok" as="div" className="grid gap-1">
            <p className="font-medium">{routeMessage(submit.data)}</p>
            <p className="font-mono text-xs">{submit.data.data.description_id}</p>
            <p>
              O registro aparece no acervo quando a transferência rodar. Até lá, ele está no staging e o
              dossiê ainda pode responder “não encontrado”.
            </p>
            <Link to="/acervo/$descriptionId" params={{ descriptionId: submit.data.data.description_id }}>
              Abrir o dossiê
            </Link>
          </Notice>
        ) : null}
        {submit.error ? <ErrorState error={submit.error} /> : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            disabled={title.trim().length === 0 || submit.isPending}
            onClick={() => submit.mutate()}
          >
            {submit.isPending ? "Gravando…" : "Gravar e enviar para a fila"}
          </Button>
          <span className="text-xs text-(--color-muted)">
            id do formulário: <span className="font-mono">{descriptionId}</span>
          </span>
        </div>
      </CardBody>
    </Card>
  );
}

const CSV_STATUS_LABEL: Record<CsvRowStatus, string> = {
  ACCEPTED: "Aceita",
  DUPLICATED: "Duplicada",
  INVALID: "Inválida",
};

const CSV_STATUS_TONE: Record<CsvRowStatus, "ok" | "warn" | "danger"> = {
  ACCEPTED: "ok",
  DUPLICATED: "warn",
  INVALID: "danger",
};

/** The three kinds the registry can produce; the badge says which one this card is. */
const ORIGIN_KIND_LABEL: Record<string, string> = {
  MANUAL: "manual",
  CSV: "csv",
  SCRAPER: "scraper",
};

/**
 * Importação de um CSV sem storage.
 *
 * O arquivo é lido aqui no navegador, conferido contra o mapa que a API publica e enviado como
 * **linhas**; nada é armazenado e não existe rota multipart (#191). A conferência local é uma
 * conveniência: a API revalida cada linha e devolve o resultado por linha, inclusive quando só
 * parte do arquivo entra.
 */
function CsvImportCard() {
  const queryClient = useQueryClient();
  const spec = useQuery({ ...queries.csvImportSpec() });
  const [fileName, setFileName] = useState<string | null>(null);
  const [encoding, setEncoding] = useState<string | null>(null);
  const [delimiter, setDelimiter] = useState<CsvDelimiter>(",");
  const [source, setSource] = useState<string | null>(null);
  const [mapping, setMapping] = useState<CsvMapping | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  const submit = useMutation({
    mutationFn: () => {
      if (!mapping) throw new Error("Nenhum arquivo preparado.");
      return importCsv({ rows: toRequestBody(mapping) });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
      void queryClient.invalidateQueries({ queryKey: ["system", "runs"] });
    },
  });

  function readSource(text: string, nextDelimiter: CsvDelimiter) {
    if (!spec.data) return;
    try {
      const parsed = parseCsv(text, { delimiter: nextDelimiter });
      setMapping(mapCsv(parsed, spec.data, () => `csv-${crypto.randomUUID()}`));
      setParseError(null);
    } catch (error) {
      setMapping(null);
      setParseError(error instanceof CsvParseError ? error.message : "Não foi possível ler o arquivo.");
    }
  }

  async function onFile(file: File | null) {
    submit.reset();
    setMapping(null);
    setParseError(null);
    setSource(null);
    setFileName(file?.name ?? null);
    setEncoding(null);
    if (!file || !spec.data) return;

    if (file.size > spec.data.max_bytes) {
      const limitMb = spec.data.max_bytes / (1024 * 1024);
      setParseError(
        `O arquivo tem ${(file.size / (1024 * 1024)).toFixed(1)} MB; o limite é ${limitMb} MB. Divida-o em partes.`,
      );
      return;
    }

    const decoded = decodeCsv(await file.arrayBuffer());
    const detected = detectDelimiter(decoded.text);
    setSource(decoded.text);
    setEncoding(decoded.encoding);
    setDelimiter(detected);
    readSource(decoded.text, detected);
  }

  function onDelimiterChange(next: CsvDelimiter) {
    setDelimiter(next);
    if (source) {
      submit.reset();
      readSource(source, next);
    }
  }

  function downloadTemplate() {
    if (!spec.data) return;
    const blob = new Blob([`\uFEFF${buildTemplate(spec.data)}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "modelo-importacao.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const limitMb = spec.data ? spec.data.max_bytes / (1024 * 1024) : 0;
  const warned = mapping?.rows.filter((row) => row.issues.length > 0).length ?? 0;

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-center justify-between gap-2 text-sm font-semibold">
        <span>Importação CSV</span>
        <Badge tone="accent">PENDING_AI</Badge>
      </CardHeader>
      <CardBody className="grid gap-3">
        <p className="text-xs text-(--color-muted)">
          O arquivo é lido aqui no navegador e enviado como linhas — <strong>nada vai para o storage</strong>.
          As linhas aceitas entram no mesmo staging e na mesma fila de IA das outras origens; a
          transferência entra na fila depois delas.
        </p>

        {spec.error ? <ErrorState error={spec.error} /> : null}
        {spec.isPending ? <Skeleton className="h-24" /> : null}

        {spec.data ? (
          <>
            <div className="flex flex-wrap items-end gap-3">
              <Field
                label="Arquivo CSV"
                hint={`Até ${formatCount(spec.data.max_rows)} linhas e ${limitMb} MB. A primeira linha é o cabeçalho.`}
              >
                <Input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(event) => {
                    const file = event.target.files?.[0] ?? null;
                    event.target.value = "";
                    void onFile(file);
                  }}
                />
              </Field>
              <Field label="Separador" className="w-44">
                <Select value={delimiter} onChange={(event) => onDelimiterChange(event.target.value as CsvDelimiter)}>
                  <option value=",">Vírgula</option>
                  <option value=";">Ponto e vírgula</option>
                </Select>
              </Field>
              <Button size="sm" variant="ghost" onClick={downloadTemplate}>
                Baixar modelo
              </Button>
            </div>

            {fileName ? (
              <p className="text-xs text-(--color-muted)">
                {fileName}
                {encoding ? ` · ${encoding}` : ""} · separador {delimiter === "," ? "vírgula" : "ponto e vírgula"}
              </p>
            ) : null}

            {parseError ? <Notice tone="danger">{parseError}</Notice> : null}

            {mapping ? (
              <div className="grid gap-2">
                <div className="flex flex-wrap gap-1">
                  {mapping.headers.map((header, index) => (
                    <Badge
                      key={`${index}-${header.header}`}
                      tone={header.isId || header.field ? "ok" : "warn"}
                      title={header.field?.help}
                    >
                      {header.header}
                      {header.isId ? " · identificador" : header.field ? ` → ${header.field.label}` : " · fora do mapa"}
                    </Badge>
                  ))}
                </div>

                {mapping.unknownHeaders.length > 0 ? (
                  <Notice tone="warn">
                    Estas colunas não fazem parte do mapa e não serão importadas:{" "}
                    <strong>{mapping.unknownHeaders.join(", ")}</strong>.
                  </Notice>
                ) : null}

                {mapping.blocking.slice(0, 8).map((message, index) => (
                  <Notice key={index} tone="danger">
                    {message}
                  </Notice>
                ))}
                {mapping.blocking.length > 8 ? (
                  <p className="text-xs text-(--color-danger)">e mais {mapping.blocking.length - 8} problemas no arquivo.</p>
                ) : null}

                {mapping.rows.length > 0 ? (
                  <div className="overflow-x-auto rounded-md ring-1 ring-(--color-line)">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-black/[0.02] text-(--color-muted)">
                        <tr>
                          <th className="px-2 py-1 font-medium">Linha</th>
                          <th className="px-2 py-1 font-medium">Identificador</th>
                          <th className="px-2 py-1 font-medium">Título</th>
                          <th className="px-2 py-1 font-medium">Prévia local</th>
                        </tr>
                      </thead>
                      <tbody>
                        {mapping.rows.slice(0, 5).map((row) => (
                          <tr key={row.line} className="border-t border-(--color-line)/60 align-top">
                            <td className="px-2 py-1 tabular-nums">{row.line}</td>
                            <td className="px-2 py-1 font-mono text-[11px]">{row.descriptionId}</td>
                            <td className="px-2 py-1">{row.title || "—"}</td>
                            <td className="px-2 py-1">
                              {row.issues.length > 0 ? (
                                <span className="text-(--color-danger)">{row.issues.join(" ")}</span>
                              ) : (
                                <span className="text-(--color-ok)">ok</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}

                {mapping.rows.length > 5 ? (
                  <p className="text-[11px] text-(--color-muted)">
                    Prévia das 5 primeiras de {formatCount(mapping.rows.length)} linhas.
                  </p>
                ) : null}

                {mapping.rows.length > 0 && warned > 0 ? (
                  <p className="text-xs text-(--color-warn)">
                    {formatCount(warned)} linha(s) com aviso local; a API confirma o resultado de cada uma.
                  </p>
                ) : null}
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="primary"
                disabled={!mapping || mapping.blocking.length > 0 || submit.isPending}
                onClick={() => submit.mutate()}
              >
                {submit.isPending
                  ? "Importando…"
                  : mapping
                    ? `Importar ${formatCount(mapping.rows.length)} linhas`
                    : "Importar"}
              </Button>
              {mapping && mapping.blocking.length > 0 ? (
                <span className="text-xs text-(--color-muted)">Corrija o arquivo antes de enviar.</span>
              ) : null}
            </div>

            {submit.error ? <ErrorState error={submit.error} /> : null}

            {submit.data ? (
              <Notice tone={submit.data.data.accepted > 0 ? "ok" : "warn"} as="div" className="grid gap-2">
                <p className="font-medium">{routeMessage(submit.data)}</p>
                <p>
                  O dossiê só encontra o registro depois que a transferência rodar; até lá, ele está no
                  staging e a fila de IA ainda não o viu.
                </p>
                <div className="overflow-x-auto rounded-md ring-1 ring-(--color-line)">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-black/[0.02] text-(--color-muted)">
                      <tr>
                        <th className="px-2 py-1 font-medium">Linha</th>
                        <th className="px-2 py-1 font-medium">Identificador</th>
                        <th className="px-2 py-1 font-medium">Título</th>
                        <th className="px-2 py-1 font-medium">Resultado</th>
                        <th className="px-2 py-1 font-medium">Motivo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(submit.data.data.rows ?? []).map((row) => {
                        const preview = mapping?.rows.find((candidate) => candidate.line === row.line);
                        return (
                          <tr key={`${row.line}-${row.description_id}`} className="border-t border-(--color-line)/60 align-top">
                            <td className="px-2 py-1 tabular-nums">{row.line}</td>
                            <td className="px-2 py-1 font-mono text-[11px]">
                              {row.status === "ACCEPTED" ? (
                                <Link to="/acervo/$descriptionId" params={{ descriptionId: row.description_id }}>
                                  {row.description_id}
                                </Link>
                              ) : (
                                row.description_id
                              )}
                            </td>
                            <td className="px-2 py-1">{preview?.title || "—"}</td>
                            <td className="px-2 py-1">
                              <Badge tone={CSV_STATUS_TONE[row.status]}>{CSV_STATUS_LABEL[row.status]}</Badge>
                            </td>
                            <td className="px-2 py-1 text-(--color-muted)">
                              {(row.issues ?? []).map((issue) => issue.message).join(" ") || "—"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Notice>
            ) : null}
          </>
        ) : null}
      </CardBody>
    </Card>
  );
}

function OriginCard({ origin, canOperate }: { origin: IngestionOrigin; canOperate: boolean }) {
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<"none" | "config" | "schedule">("none");

  const active = origin.active_run_id != null;
  const controlled = canOperate;

  return (
    <Disclosure
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setPanel("none");
      }}
      header={<OriginHeader origin={origin} />}
      actions={
        controlled ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => setPanel(panel === "config" ? "none" : "config")}>
              Configurar
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPanel(panel === "schedule" ? "none" : "schedule")}>
              Agenda
            </Button>
          </div>
        ) : null
      }
      toggleLabel="Ver fila, execução e configuração"
    >
      <div className="grid gap-3">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <Fact label="Fila">
            <span className="text-2xl leading-none font-semibold tabular-nums">
              {origin.pending == null ? "—" : formatCount(origin.pending)}
            </span>
            <p className="mt-1 text-xs text-(--color-muted)">
              {origin.pending_reason ?? "O que a próxima execução desta origem leria."}
            </p>
          </Fact>
          <Fact label="Processados">
            <span className="text-2xl leading-none font-semibold tabular-nums">
              {origin.processed == null ? "—" : formatCount(origin.processed)}
            </span>
            <p className="mt-1 text-xs text-(--color-muted)">
              {origin.failed ? `${formatCount(origin.failed)} com falha terminal` : "sem falha terminal"}
            </p>
          </Fact>
          <Fact label="Última execução">
            {origin.last_run_id == null ? (
              <span className="text-sm text-(--color-muted)">nenhuma</span>
            ) : (
              <>
                <span className="flex flex-wrap items-center gap-1">
                  {origin.last_run_status ? (
                    <Badge tone={RUN_STATUS_TONE[origin.last_run_status]}>
                      {RUN_STATUS_LABEL[origin.last_run_status]}
                    </Badge>
                  ) : null}
                  <span className="text-xs text-(--color-muted)">#{origin.last_run_id}</span>
                </span>
                <p className="mt-1 text-xs text-(--color-muted)">{formatDateTime(origin.last_run_at)}</p>
                {origin.last_run_error ? (
                  <p className="mt-1 line-clamp-2 text-xs text-(--color-danger)">{origin.last_run_error}</p>
                ) : null}
              </>
            )}
          </Fact>
          <Fact label="Agenda">
            {origin.schedule?.cron ? (
              <>
                <span className="font-mono text-xs">{origin.schedule.cron}</span>
                <p className="mt-1 text-xs text-(--color-muted)">
                  {origin.schedule.timezone} · próxima {formatDateTime(origin.schedule.next_run_at)}
                </p>
              </>
            ) : (
              <span className="text-sm text-(--color-muted)">sem agenda</span>
            )}
          </Fact>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {controlled ? (
            <RunNowButton origin={origin} disabled={active} />
          ) : (
            <p className="text-xs text-(--color-muted)">
              A configuração, a agenda e a execução são do operador; a entrada manual está disponível acima.
            </p>
          )}
          {active ? (
            <Badge tone="accent">
              {origin.active_run_status ? RUN_STATUS_LABEL[origin.active_run_status] : "em execução"} #{origin.active_run_id}
            </Badge>
          ) : null}
          {origin.runner_available ? (
            <Badge tone="ok">runner disponível</Badge>
          ) : (
            <Badge tone="warn">nenhum runner aceita ingestão</Badge>
          )}
        </div>

        {panel === "config" && controlled ? <OriginConfigForm origin={origin} /> : null}
        {panel === "schedule" && controlled ? <OriginScheduleForm origin={origin} /> : null}
      </div>
    </Disclosure>
  );
}

function OriginHeader({ origin }: { origin: IngestionOrigin }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm font-medium">{origin.label}</span>
      <Badge tone="neutral">{ORIGIN_KIND_LABEL[origin.kind] ?? origin.kind.toLowerCase()}</Badge>
      <Badge tone={origin.enabled ? "ok" : "neutral"}>{origin.enabled ? "ativa" : "pausada"}</Badge>
      <span className="text-xs text-(--color-muted)">{origin.description}</span>
    </div>
  );
}

function RunNowButton({ origin, disabled }: { origin: IngestionOrigin; disabled: boolean }) {
  const queryClient = useQueryClient();
  const run = useMutation({
    mutationFn: () =>
      triggerIngestionRun(origin.code, {
        force_retry_fatal: false,
        ignore_sliding_window: false,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
      void queryClient.invalidateQueries({ queryKey: ["system", "runs"] });
    },
  });

  return (
    <div className="grid gap-1">
      <Button size="sm" variant="primary" disabled={disabled || run.isPending} onClick={() => run.mutate()}>
        {disabled ? "Já há uma execução" : run.isPending ? "Enfileirando…" : "Enfileirar execução"}
      </Button>
      {run.data ? (
        <span className="text-xs text-(--color-muted)">
          Execução #{run.data.run_id} na fila; um runner a pega quando estiver livre.
        </span>
      ) : null}
      {run.error ? <ErrorState error={run.error} /> : null}
    </div>
  );
}

function OriginConfigForm({ origin }: { origin: IngestionOrigin }) {
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(origin.enabled);
  const configFields = origin.config_fields ?? [];
  const optionFields = origin.option_fields ?? [];
  const [config, setConfig] = useState<Record<string, string | number | boolean>>(() =>
    initialConfig(configFields, origin.config ?? {}),
  );
  const [options, setOptions] = useState<Record<string, string | boolean>>(() =>
    initialOptions(optionFields, origin.options ?? {}),
  );

  const save = useMutation({
    mutationFn: () =>
      updateIngestionOrigin(origin.code, {
        enabled,
        config: configValues(configFields, config),
        options: optionValues(optionFields, options),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
    },
  });

  return (
    <div className="grid gap-3 rounded-md bg-black/[0.02] p-3 ring-1 ring-(--color-line)">
      <label className="flex items-center gap-2 text-xs">
        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
        Origem ativa (uma origem pausada não lista, não agenda e não aceita entrada manual)
      </label>

      {configFields.length === 0 ? (
        <p className="text-xs text-(--color-muted)">Esta origem não tem configuração de adapter.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {configFields.map((field) => (
            <Field key={field.name} label={field.label}>
              {field.kind === "boolean" ? (
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={Boolean(config[field.name])}
                    onChange={(event) => setConfig({ ...config, [field.name]: event.target.checked })}
                  />
                  {field.help}
                </label>
              ) : (
                <>
                  <Input
                    type={field.kind === "number" ? "number" : "text"}
                    value={String(config[field.name] ?? "")}
                    onChange={(event) => setConfig({ ...config, [field.name]: event.target.value })}
                  />
                  <span className="text-[11px] text-(--color-muted)">{field.help}</span>
                </>
              )}
            </Field>
          ))}
        </div>
      )}

      {optionFields.length > 0 ? (
        <details className="grid gap-2">
          <summary className="cursor-pointer text-xs font-medium">Opções da execução agendada</summary>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            {optionFields.map((option) => (
              <Field key={option.name} label={option.label}>
                {option.kind === "boolean" ? (
                  <label className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={Boolean(options[option.name])}
                      onChange={(event) => setOptions({ ...options, [option.name]: event.target.checked })}
                    />
                    {option.help}
                  </label>
                ) : (
                  <>
                    <Input
                      type="number"
                      value={String(options[option.name] ?? "")}
                      onChange={(event) => setOptions({ ...options, [option.name]: event.target.value })}
                    />
                    <span className="text-[11px] text-(--color-muted)">{option.help}</span>
                  </>
                )}
              </Field>
            ))}
          </div>
        </details>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="primary" disabled={save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Salvando…" : "Salvar configuração"}
        </Button>
        {save.data ? <span className="text-xs text-(--color-muted)">Configuração salva.</span> : null}
      </div>
      {save.error ? <ErrorState error={save.error} /> : null}
    </div>
  );
}

function OriginScheduleForm({ origin }: { origin: IngestionOrigin }) {
  const queryClient = useQueryClient();
  const [cron, setCron] = useState(origin.schedule?.cron ?? "0 2 * * *");
  const [timezone, setTimezone] = useState(origin.schedule?.timezone ?? "America/Sao_Paulo");

  const save = useMutation({
    mutationFn: () => saveIngestionSchedule(origin.code, { cron: cron.trim(), timezone: timezone.trim() || null }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteIngestionSchedule(origin.code),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
    },
  });

  return (
    <div className="grid gap-3 rounded-md bg-black/[0.02] p-3 ring-1 ring-(--color-line)">
      <p className="text-xs text-(--color-muted)">
        Cinco campos (minuto, hora, dia do mês, mês, dia da semana), avaliados na zona indicada. Um período
        que chega com uma ingestão ativa é <strong>pulado</strong>, não enfileirado.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Cron">
          <Input value={cron} onChange={(event) => setCron(event.target.value)} placeholder="0 2 * * *" />
        </Field>
        <Field label="Fuso IANA">
          <Input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="America/Sao_Paulo" />
        </Field>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="primary" disabled={save.isPending || cron.trim().length === 0} onClick={() => save.mutate()}>
          {save.isPending ? "Salvando…" : "Salvar agenda"}
        </Button>
        <Button size="sm" variant="ghost" disabled={remove.isPending || !origin.schedule} onClick={() => remove.mutate()}>
          Remover agenda
        </Button>
      </div>
      {save.error ? <ErrorState error={save.error} /> : null}
      {remove.error ? <ErrorState error={remove.error} /> : null}
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md bg-black/[0.02] px-3 py-2 ring-1 ring-(--color-line)">
      <span className="text-[11px] font-semibold tracking-wide text-(--color-muted) uppercase">{label}</span>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function initialConfig(fields: OriginConfigField[], values: Record<string, unknown>): Record<string, string | number | boolean> {
  return Object.fromEntries(
    fields.map((field) => {
      const value = values[field.name] ?? field.default ?? "";
      return [field.name, field.kind === "boolean" ? Boolean(value) : typeof value === "number" ? value : String(value)];
    }),
  );
}

function configValues(
  fields: OriginConfigField[],
  values: Record<string, string | number | boolean>,
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.name];
    if (value === "" || value == null) continue;
    result[field.name] = field.kind === "number" ? Number(value) : value;
  }
  return result;
}

function initialOptions(fields: IngestionOption[], values: Record<string, unknown>): Record<string, string | boolean> {
  return Object.fromEntries(
    fields.map((field) => {
      const value = values[field.name] ?? field.default ?? "";
      return [field.name, field.kind === "boolean" ? Boolean(value) : String(value)];
    }),
  );
}

function optionValues(fields: IngestionOption[], values: Record<string, string | boolean>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.name];
    if (value === "" || value == null) continue;
    if (field.kind === "boolean" && value === false) continue;
    result[field.name] = field.kind === "boolean" ? value : Number(value);
  }
  return result;
}
