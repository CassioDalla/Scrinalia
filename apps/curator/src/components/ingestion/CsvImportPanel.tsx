import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { importCsv, type CsvRowStatus } from "@/api/client";
import { queries } from "@/api/queries";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Hint } from "@/components/ui/Hint";
import { Input, Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { CsvParseError, decodeCsv, detectDelimiter, parseCsv, type CsvDelimiter } from "@/lib/csv";
import { buildTemplate, mapCsv, toRequestBody, type CsvMapping } from "@/lib/csvImport";
import { formatCount } from "@/lib/format";
import { routeMessage } from "@/lib/messages";

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

/**
 * Importação de um CSV sem storage: the **Importar CSV** tab of `/acervo/nova`.
 *
 * O arquivo é lido aqui no navegador, conferido contra o mapa que a API publica e enviado como
 * **linhas**; nada é armazenado e não existe rota multipart (#191). A conferência local é uma
 * conveniência: a API revalida cada linha e devolve o resultado por linha, inclusive quando só
 * parte do arquivo entra. O destino é o mesmo da outra aba — staging e fila de IA —, e o cabeçalho
 * da tela diz isso uma vez.
 */
export function CsvImportPanel() {
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
        {/*
          The template belongs to the card, not to the row of fields: beside them it was a third
          control in a line of two, and `items-end` aligned it with the hint under the file input.
        */}
        <Button size="sm" variant="ghost" onClick={downloadTemplate} disabled={!spec.data}>
          Baixar Modelo
        </Button>
      </CardHeader>
      <CardBody className="grid gap-3">
        <p className="text-xs text-(--color-muted)">
          Arraste ou selecione sua planilha. O sistema lê os dados na hora para conferir se está tudo certo antes de enviar para a sua central de revisão.
        </p>

        {spec.error ? <ErrorState error={spec.error} /> : null}
        {spec.isPending ? <Skeleton className="h-24" /> : null}

        {spec.data ? (
          <>
            {/*
              `items-start`, not `items-end`: the two fields have different heights by design — the
              file input carries a hint and the separator does not — and bottom-aligning the columns
              pushed the shorter one's label down, so the two controls sat on different lines.
            */}
            <div className="flex flex-wrap items-start gap-3">
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
                    <span key={`${index}-${header.header}`} className="inline-flex items-center gap-1">
                      <Badge tone={header.isId || header.field ? "ok" : "warn"}>
                        {header.header}
                        {header.isId ? " · identificador" : header.field ? ` → ${header.field.label}` : " · fora do mapa"}
                      </Badge>
                      {header.field?.help ? (
                        <Hint label={`Sobre a coluna ${header.header}`} align="start">
                          {header.field.help}
                        </Hint>
                      ) : null}
                    </span>
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
                  O dossiê só encontra o registro depois que a transferência rodar; até lá, ele ainda
                  não aparece no acervo e a revisão por IA não começou.
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
