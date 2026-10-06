import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createCleaningRule,
  deactivateCleaningRule,
  previewCleaningRule,
  type CleaningRuleDryRun,
  type CleaningTargetColumn,
  type CreateCleaningRuleRequest,
  type RuleKind,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Input, Select } from "@/components/ui/Input";
import { formatCount } from "@/lib/format";
import { labelOf } from "@/lib/hierarchy";
import { RULE_KIND_HINT, RULE_KIND_LABEL, RULE_KIND_TONE, TARGET_COLUMN_LABEL } from "@/lib/quality";

const TARGETS: CleaningTargetColumn[] = [
  "original_title",
  "scope_content",
  "admin_bio_history",
  "provenance",
  "archivist_notes",
];
const KINDS: RuleKind[] = ["REWRITE", "VALIDATE", "LLM_CHECK"];

/**
 * The cleaning rules: the one place a regular expression can rewrite the collection.
 *
 * ``rule_kind`` is the difference between cleaning and destroying, and the screen makes the choice
 * explicit instead of leaving it implied: ``REWRITE`` replaces every match, while
 * ``VALIDATE``/``LLM_CHECK`` only flag it. The worker filters ``REWRITE`` explicitly — without that
 * a validation rule would rewrite the text.
 *
 * The screen also takes the dry run seriously, for a reason from this collection's own history: a
 * test rule (``aaaaa``, ``\\bpalavra\\b``) sat active and stamped all 3,608 documents. It never
 * matched anything, but nothing on the old surface made an active rule look dangerous. Here an
 * active rule is the loudest thing on the screen, and nothing is saved before the preview.
 */
export function CleaningRulesRoute() {
  const queryClient = useQueryClient();
  const rules = useQuery(queries.cleaningRules());

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["quality", "cleaning-rules"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const deactivate = useMutation({
    mutationFn: (ruleId: number) => deactivateCleaningRule(ruleId),
    onSuccess: invalidate,
  });

  const rows = rules.data ?? [];

  return (
    <>
      <PageHeader
        title="Regras de limpeza"
        subtitle={
          rules.data
            ? rows.length === 0
              ? "Nenhuma regra ativa"
              : `${formatCount(rows.length)} regras ativas`
            : "Lendo as regras…"
        }
      />

      <div className="grid max-w-5xl gap-4 px-6 py-5">
        <p className="rounded-md bg-(--color-warn)/5 px-3 py-2 text-xs text-(--color-warn) ring-1 ring-(--color-warn)/20">
          <strong>O tipo da regra é o que separa limpar de destruir.</strong> Uma regra{" "}
          <code>REWRITE</code> substitui cada ocorrência no acervo; <code>VALIDATE</code> e{" "}
          <code>LLM_CHECK</code> só sinalizam — o worker filtra <code>REWRITE</code> explicitamente.
          Regras nunca são apagadas: desativar é o caminho reversível.
        </p>

        {rules.error ? <ErrorState error={rules.error} /> : null}
        {rules.isPending ? <Spinner /> : null}

        {rules.data && rows.length === 0 ? (
          <EmptyState
            title="Nenhuma regra ativa"
            hint="Sem regra REWRITE ativa, o worker de limpeza não reescreve nada. Sem regra VALIDATE/LLM_CHECK, a fila de anomalias fica vazia por construção — não por o acervo estar perfeito."
          />
        ) : null}

        <ul className="grid gap-2">
          {rows.map((rule) => (
            <li key={rule.rule_id}>
              <Card className={rule.rule_kind === "REWRITE" ? "ring-(--color-warn)/40" : undefined}>
                <CardBody className="grid gap-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{rule.rule_name}</span>
                      <Badge tone={RULE_KIND_TONE[rule.rule_kind] ?? "neutral"} title={RULE_KIND_HINT[rule.rule_kind]}>
                        {labelOf(RULE_KIND_LABEL, rule.rule_kind)}
                      </Badge>
                      <Badge tone="neutral">{labelOf(TARGET_COLUMN_LABEL, rule.target_column)}</Badge>
                      <Badge tone="ok">ativa</Badge>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={deactivate.isPending}
                      onClick={() => deactivate.mutate(rule.rule_id)}
                    >
                      desativar
                    </Button>
                  </div>

                  <div className="flex flex-wrap items-center gap-3 text-xs text-(--color-muted)">
                    <span>
                      expressão: <code className="rounded bg-black/[0.05] px-1">{rule.regex_pattern}</code>
                    </span>
                    <span>
                      substitui por:{" "}
                      <code className="rounded bg-black/[0.05] px-1">
                        {rule.replacement_string === "" ? "(vazio)" : rule.replacement_string}
                      </code>
                    </span>
                    {rule.anomaly_reason ? <span>motivo da anomalia: {rule.anomaly_reason}</span> : null}
                    {rule.engine_name ? <span>engine: {rule.engine_name}</span> : null}
                  </div>

                  {rule.rule_kind === "REWRITE" ? (
                    <p className="text-xs text-(--color-warn)">
                      Esta regra reescreve o acervo: cada ocorrência em{" "}
                      {labelOf(TARGET_COLUMN_LABEL, rule.target_column)} será substituída na próxima
                      varredura.
                    </p>
                  ) : null}
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>

        <CreateRuleCard onCreated={invalidate} />
      </div>
    </>
  );
}

function CreateRuleCard({ onCreated }: { onCreated: () => void }) {
  const [draft, setDraft] = useState<CreateCleaningRuleRequest>({
    rule_name: "",
    target_column: "original_title",
    regex_pattern: "",
    replacement_string: "",
    rule_kind: "REWRITE",
    anomaly_reason: null,
    engine_name: null,
    preset: null,
  });
  const [preview, setPreview] = useState<CleaningRuleDryRun | null>(null);

  const dryRun = useMutation({
    mutationFn: () =>
      previewCleaningRule({
        target_column: draft.target_column,
        regex_pattern: draft.regex_pattern,
        replacement_string: draft.replacement_string ?? "",
      }),
    onSuccess: setPreview,
  });

  const create = useMutation({
    mutationFn: () => createCleaningRule(draft),
    onSuccess: () => {
      setDraft({
        rule_name: "",
        target_column: "original_title",
        regex_pattern: "",
        replacement_string: "",
        rule_kind: "REWRITE",
        anomaly_reason: null,
        engine_name: null,
        preset: null,
      });
      setPreview(null);
      onCreated();
    },
  });

  const valid = draft.rule_name.trim().length > 0 && draft.regex_pattern.trim().length > 0;
  // A rule that rewrites is only saved after the dry run: the preview is the step, not a nicety.
  const rewriteNeedsPreview = draft.rule_kind === "REWRITE" && preview?.is_valid_regex !== true;
  const canSave = valid && !rewriteNeedsPreview && !create.isPending;

  const patch = (changes: Partial<CreateCleaningRuleRequest>) => {
    setPreview(null);
    setDraft((current) => ({ ...current, ...changes }));
  };

  return (
    <Card>
      <CardHeader className="text-sm font-semibold">Nova regra</CardHeader>
      <CardBody className="grid gap-2">
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Nome</span>
            <Input
              value={draft.rule_name}
              onChange={(event) => patch({ rule_name: event.target.value })}
              maxLength={150}
              placeholder="ex.: normaliza abreviação de logradouro"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Coluna alvo</span>
            <Select
              value={draft.target_column}
              onChange={(event) => patch({ target_column: event.target.value as CleaningTargetColumn })}
            >
              {TARGETS.map((target) => (
                <option key={target} value={target}>
                  {labelOf(TARGET_COLUMN_LABEL, target)}
                </option>
              ))}
            </Select>
          </label>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Expressão regular (Python)</span>
            <Input
              value={draft.regex_pattern}
              onChange={(event) => patch({ regex_pattern: event.target.value })}
              placeholder={String.raw`\bav\b\.?`}
              className="font-mono"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Substituir por (vazio = apagar)</span>
            <Input
              value={draft.replacement_string ?? ""}
              onChange={(event) => patch({ replacement_string: event.target.value })}
              className="font-mono"
            />
          </label>
        </div>

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Tipo</span>
          <Select value={draft.rule_kind} onChange={(event) => patch({ rule_kind: event.target.value as RuleKind })}>
            {KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {labelOf(RULE_KIND_LABEL, kind)}
              </option>
            ))}
          </Select>
          <span className="text-(--color-muted)">{RULE_KIND_HINT[draft.rule_kind ?? "REWRITE"]}</span>
        </label>

        {draft.rule_kind === "VALIDATE" ? (
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Motivo gravado no documento quando casar</span>
            <Input
              value={draft.anomaly_reason ?? ""}
              onChange={(event) => patch({ anomaly_reason: event.target.value || null })}
              placeholder="ex.: título fora do padrão"
            />
          </label>
        ) : null}

        {draft.rule_kind === "LLM_CHECK" ? (
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-(--color-muted)">Engine</span>
              <Input
                value={draft.engine_name ?? ""}
                onChange={(event) => patch({ engine_name: event.target.value || null })}
                placeholder="ex.: ollama"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="text-(--color-muted)">Preset</span>
              <Input
                value={draft.preset ?? ""}
                onChange={(event) => patch({ preset: event.target.value || null })}
              />
            </label>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={!valid || dryRun.isPending}
            onClick={() => dryRun.mutate()}
          >
            {dryRun.isPending ? "Simulando…" : "Conferir impacto"}
          </Button>
          <Button
            size="sm"
            variant="primary"
            disabled={!canSave}
            title={rewriteNeedsPreview ? "Confira o impacto antes: esta regra reescreve o acervo" : undefined}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Salvando…" : "Salvar e ativar"}
          </Button>
          {rewriteNeedsPreview ? (
            <span className="text-xs text-(--color-muted)">
              uma regra que reescreve só é salva depois de conferir o impacto
            </span>
          ) : null}
        </div>

        {preview ? (
          <div className="rounded-md bg-black/[0.03] px-3 py-2 text-xs">
            {preview.is_valid_regex ? (
              <p>
                <strong>{formatCount(preview.matches_found)}</strong> ocorrências em{" "}
                {labelOf(TARGET_COLUMN_LABEL, draft.target_column)}.
              </p>
            ) : (
              <p className="text-(--color-danger)">
                Expressão inválida: {preview.error_message ?? "o Python não conseguiu compilá-la."}
              </p>
            )}
            {preview.samples.length > 0 ? (
              <ul className="mt-1 grid gap-1">
                {preview.samples.map((sample) => (
                  <li key={sample.description_id} className="text-(--color-muted)">
                    <code>{sample.description_id}</code>:{" "}
                    <span className="line-through">{sample.original_text.slice(0, 70)}</span> →{" "}
                    <span>{sample.modified_text.slice(0, 70)}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        {create.data ? <p className="text-xs text-(--color-muted)">{create.data.message}</p> : null}
        {create.error ? <ErrorState error={create.error} /> : null}
        {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
      </CardBody>
    </Card>
  );
}
