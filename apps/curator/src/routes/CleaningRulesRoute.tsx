import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  activateCleaningRule,
  createCleaningRule,
  deactivateCleaningRule,
  previewCleaningRule,
  type CleaningRuleDryRun,
  type CleaningRulePreset,
  type CleaningTargetColumn,
  type CreateCleaningRuleRequest,
  type RuleKind,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { ACTION } from "@/lib/copy";
import { formatCount } from "@/lib/format";
import { labelOf } from "@/lib/hierarchy";
import { RULE_KIND_HINT, RULE_KIND_LABEL, RULE_KIND_TONE, TARGET_COLUMN_LABEL } from "@/lib/quality";
import { routeMessage } from "@/lib/messages";

const TARGETS: CleaningTargetColumn[] = [
  "original_title",
  "scope_content",
  "admin_bio_history",
  "provenance",
  "archivist_notes",
];
const KINDS: RuleKind[] = ["REWRITE", "VALIDATE", "LLM_CHECK"];

/**
 * ``nome — modelo``, because the model is what the archivist is choosing between.
 *
 * The config comes from the registry's ``describe_config`` — the read-only twin of ``get_engine`` —
 * so the label states the model the run will actually load and not one re-derived from the name.
 */
function presetLabel(preset: CleaningRulePreset): string {
  const model = preset.config?.model;
  return typeof model === "string" && model.length > 0 ? `${preset.name} — ${model}` : preset.name;
}

function subtitleOf(active: number, retired: number): string {
  const activeLabel = active === 1 ? "1 regra ativa" : `${formatCount(active)} regras ativas`;
  if (retired === 0) return active === 0 ? "Nenhuma regra ativa" : activeLabel;
  const retiredLabel = retired === 1 ? "1 aposentada" : `${formatCount(retired)} aposentadas`;
  return `${active === 0 ? "Nenhuma regra ativa" : activeLabel} · ${retiredLabel}`;
}

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

  const activate = useMutation({
    mutationFn: (ruleId: number) => activateCleaningRule(ruleId),
    onSuccess: invalidate,
  });

  const rows = rules.data ?? [];
  const activeCount = rows.filter((rule) => rule.is_active).length;
  const retiredCount = rows.length - activeCount;
  // Active first: the loud ones (a REWRITE rule rewrites the collection) stay at the top, and the
  // retired ones sit at the bottom, which is where the way back lives.
  const ordered = [...rows].sort((a, b) => Number(b.is_active) - Number(a.is_active));

  return (
    <>
      <PageHeader screen="cleaningRules" pending={rules.isPending} status={rules.data ? subtitleOf(activeCount, retiredCount) : undefined} />

      <PageBody>
        <Notice tone="warn">
          <strong>O tipo da regra é o que separa limpar de destruir.</strong> Uma regra que reescreve o
          texto substitui cada ocorrência no acervo; uma que só sinaliza, ou que consulta o modelo,
          apenas aponta o problema, sem tocar no texto. Regras nunca são excluídas: as aposentadas
          continuam nesta tela, com o botão de reativar.
        </Notice>

        {rules.error ? <ErrorState error={rules.error} /> : null}
        {rules.isPending ? <Spinner /> : null}

        {rules.data && activeCount === 0 ? (
          <EmptyState
            title="Nenhuma regra ativa"
            hint="Sem nenhuma regra ativa que reescreva o texto, nada no acervo é reescrito. Sem nenhuma regra ativa que sinalize, nenhuma ocorrência é marcada pelas suas regras; as anomalias que o sistema aponta por conta própria — sem data, título vazio — continuam aparecendo. As aposentadas ficam abaixo, com o botão de reativar."
          />
        ) : null}

        {/*
          The write first. Every rule on this screen is a statement about the whole collection, and the
          archivist arrives having decided to write one; the catalogue is what they check afterwards.
          The dry run stays inside this same card, which is where it already lived: a rule that
          rewrites is only saved after the preview, and the two buttons belong together.
        */}
        <CreateRuleCard onCreated={invalidate} />

        <ul className="grid gap-2">
          {ordered.map((rule) => (
            <li key={rule.rule_id}>
              <Card className={rule.is_active && rule.rule_kind === "REWRITE" ? "ring-(--color-warn)/40" : undefined}>
                <CardBody className="grid gap-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">{rule.rule_name}</span>
                      <Badge tone={RULE_KIND_TONE[rule.rule_kind] ?? "neutral"} title={RULE_KIND_HINT[rule.rule_kind]}>
                        {labelOf(RULE_KIND_LABEL, rule.rule_kind)}
                      </Badge>
                      <Badge tone="neutral">{labelOf(TARGET_COLUMN_LABEL, rule.target_column)}</Badge>
                      <Badge tone={rule.is_active ? "ok" : "neutral"}>
                        {rule.is_active ? "ativa" : "aposentada"}
                      </Badge>
                    </div>
                    {rule.is_active ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={deactivate.isPending}
                        onClick={() => deactivate.mutate(rule.rule_id)}
                      >
                        {ACTION.retire.label}
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={activate.isPending}
                        onClick={() => activate.mutate(rule.rule_id)}
                      >
                        {ACTION.reactivate.label}
                      </Button>
                    )}
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

                  {rule.is_active && rule.rule_kind === "REWRITE" ? (
                    <p className="text-xs text-(--color-warn)">
                      Esta regra reescreve o acervo: cada ocorrência em{" "}
                      {labelOf(TARGET_COLUMN_LABEL, rule.target_column)} será substituída na próxima
                      varredura. As descrições aprovadas por uma pessoa não são tocadas.
                    </p>
                  ) : null}
                  {!rule.is_active ? (
                    <p className="text-xs text-(--color-muted)">
                      Aposentada: esta regra não é aplicada ao acervo. Reativar devolve a mesma regra —
                      nada foi excluído.
                    </p>
                  ) : null}
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>
      </PageBody>
    </>
  );
}

function CreateRuleCard({ onCreated }: { onCreated: () => void }) {
  const engines = useQuery(queries.cleaningRuleEngines());
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

  const catalogue = engines.data ?? [];
  // The preset list belongs to the chosen engine, and an empty engine means the worker's documented
  // fallback — so the select of presets follows the first engine until a person picks another.
  const chosenEngine = draft.engine_name ?? catalogue[0]?.name ?? "";
  const presets = catalogue.find((engine) => engine.name === chosenEngine)?.presets ?? [];

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
    <Disclosure
      triggerLabel="+ Nova regra"
      toggleLabel="Nova regra"
      header={
        <div className="grid gap-1">
          <span className="text-sm font-semibold">Nova regra</span>
          <span className="text-xs text-(--color-muted)">
            Uma regra que reescreve substitui cada ocorrência no acervo inteiro e só é salva depois de
            conferir o impacto.
          </span>
        </div>
      }
    >
      <div className="grid gap-2">
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Nome">
            <Input
              value={draft.rule_name}
              onChange={(event) => patch({ rule_name: event.target.value })}
              maxLength={150}
              placeholder="ex.: normaliza abreviação de logradouro"
            />
          </Field>
          <Field label="Campo da Descrição">
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
          </Field>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Expressão Regular (Python)">
            <Input
              value={draft.regex_pattern}
              onChange={(event) => patch({ regex_pattern: event.target.value })}
              placeholder={String.raw`\bav\b\.?`}
              className="font-mono"
            />
          </Field>
          <Field label="Substituir por (vazio = remover o trecho)">
            <Input
              value={draft.replacement_string ?? ""}
              onChange={(event) => patch({ replacement_string: event.target.value })}
              className="font-mono"
            />
          </Field>
        </div>

        <Field label="Tipo">
          <Select value={draft.rule_kind} onChange={(event) => patch({ rule_kind: event.target.value as RuleKind })}>
            {KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {labelOf(RULE_KIND_LABEL, kind)}
              </option>
            ))}
          </Select>
          <span className="text-(--color-muted)">{RULE_KIND_HINT[draft.rule_kind ?? "REWRITE"]}</span>
        </Field>

        {draft.rule_kind === "VALIDATE" ? (
          <Field label="Motivo Registrado no Documento quando Casar">
            <Input
              value={draft.anomaly_reason ?? ""}
              onChange={(event) => patch({ anomaly_reason: event.target.value || null })}
              placeholder="ex.: título fora do padrão"
            />
          </Field>
        ) : null}

        {draft.rule_kind === "LLM_CHECK" ? (
          <div className="grid gap-2 sm:grid-cols-2">
            <Field label="Motor">
              <Select
                value={draft.engine_name ?? ""}
                disabled={catalogue.length === 0}
                onChange={(event) => patch({ engine_name: event.target.value || null, preset: null })}
              >
                <option value="">
                  {engines.isPending ? "carregando…" : `padrão (${catalogue[0]?.name ?? "nenhum motor"})`}
                </option>
                {catalogue.map((engine) => (
                  <option key={engine.name} value={engine.name}>
                    {engine.name}
                  </option>
                ))}
              </Select>
              <span className="text-(--color-muted)">
                Em branco, a regra usa o motor padrão. Só é possível salvar com um motor desta lista.
              </span>
            </Field>
            <Field label="Preset">
              <Select
                value={draft.preset ?? ""}
                disabled={presets.length === 0}
                onChange={(event) => patch({ preset: event.target.value || null })}
              >
                <option value="">sem preset (o padrão do motor)</option>
                {presets.map((preset) => (
                  <option key={preset.name} value={preset.name}>
                    {presetLabel(preset)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={!valid || dryRun.isPending}
            onClick={() => dryRun.mutate()}
          >
            {dryRun.isPending ? ACTION.preview.pending : ACTION.preview.label}
          </Button>
          <Button
            size="sm"
            variant="primary"
            disabled={!canSave}
            title={rewriteNeedsPreview ? "Confira o impacto antes: esta regra reescreve o acervo" : undefined}
            onClick={() => create.mutate()}
          >
            {create.isPending ? ACTION.save.pending : "Salvar e ativar"}
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
                A amostra encontrou{" "}
                <strong>{formatCount(preview.matches_found)}</strong> descrições que mudariam em{" "}
                {labelOf(TARGET_COLUMN_LABEL, draft.target_column)}.
              </p>
            ) : (
              <p className="text-(--color-danger)">
                Expressão inválida: {preview.error_message ?? "a expressão não pôde ser lida."}
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

        {create.data ? <p className="text-xs text-(--color-muted)">{routeMessage(create.data)}</p> : null}
        {create.error ? <ErrorState error={create.error} /> : null}
        {dryRun.error ? <ErrorState error={dryRun.error} /> : null}
      </div>
    </Disclosure>
  );
}
