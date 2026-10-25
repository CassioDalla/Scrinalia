import type { WorkerOption, WorkerSettings } from "@/api/client";
import { Field } from "@/components/ui/Field";
import { Input } from "@/components/ui/Input";

/**
 * The declared options of a worker, rendered as controls instead of a JSON box (issue #120).
 *
 * The contract now says what a worker accepts: `settings.declared_options` carries the name, the
 * kind, the default and — for a column list — the columns the AI text has. The screen renders one
 * control per option from that list, so it cannot offer a key the write path would refuse, and the
 * archivist never has to know that the option is called `columns_to_classify`.
 *
 * Two modes, because the two screens mean different things by an empty field:
 *
 * * `settings` — the body **replaces** the persisted row: a field left empty is the code default, and
 *   an unchecked flag removes the key. There is no `limit` here: a cap belongs to one execution.
 * * `run` — the body **overrides** one execution: a flag is always sent (unchecking the box is a
 *   decision to turn off a persisted `force`), and an empty field still means "the default".
 *
 * The labels are Portuguese because a person reads them; the option's name stays visible under the
 * control, because the operator reads it in the guide and on the command line.
 */

/** The Portuguese label of an option, and the one-line explanation under it. */
const COPY: Record<string, { label: string; hint?: string }> = {
  columns_to_extract: {
    label: "Colunas lidas pela IA",
    hint: "O texto que o worker lê. Vazio = a escolha do código.",
  },
  columns_to_classify: {
    label: "Colunas lidas pela IA",
    hint: "O texto que o worker lê. Vazio = a escolha do código.",
  },
  confidence_threshold: {
    label: "Limite de confiança",
    hint: "Abaixo dele o resultado não é vinculado.",
  },
  force: {
    label: "Forçar",
    hint: "Re-lê o que já foi carimbado por outro produtor.",
  },
  limit: {
    label: "Limite de documentos",
    hint: "Vale só para esta execução; não vira padrão.",
  },
  repeat_threshold: {
    label: "Repetições para tratar como modelo",
    hint: "Quantos títulos iguais caracterizam um resto de modelo.",
  },
  llm_confidence: {
    label: "Confiança mínima do LLM",
    hint: "Abaixo dela a revisão de título é descartada.",
  },
  similarity_threshold: {
    label: "Similaridade mínima",
    hint: "O trigram entre a tag e a entidade para entrar no julgamento.",
  },
  auto_resolve_threshold: {
    label: "Confiança para resolver sozinho",
    hint: "Abaixo dela o conflito vai para a fila de revisão.",
  },
};

type OptionsMode = "settings" | "run";

function labelOf(option: WorkerOption): { label: string; hint?: string } {
  return COPY[option.name] ?? { label: option.name };
}

/** The options this screen may show: the run cap is not a default. */
export function optionsForMode(options: WorkerOption[], mode: OptionsMode): WorkerOption[] {
  return mode === "settings" ? options.filter((option) => option.scope !== "run") : options;
}

/**
 * The values the form starts from: the persisted defaults, restricted to what this screen edits.
 *
 * A stale persisted key that the option list does not carry is dropped here — the read already says
 * it was ignored, and re-sending it would keep the row dirty forever.
 */
export function initialOptionValues(
  persisted: Record<string, unknown>,
  options: WorkerOption[],
  mode: OptionsMode,
): Record<string, unknown> {
  const allowed = new Set(optionsForMode(options, mode).map((option) => option.name));
  return Object.fromEntries(Object.entries(persisted).filter(([key]) => allowed.has(key)));
}

/** The request body's `options`: empty fields are not sent, so they keep following the default. */
export function optionsForRequest(
  values: Record<string, unknown>,
  options: WorkerOption[],
  mode: OptionsMode,
): Record<string, unknown> {
  const visible = optionsForMode(options, mode);
  const body: Record<string, unknown> = {};
  for (const option of visible) {
    const value = values[option.name];
    if (value === undefined || value === null || value === "") continue;
    body[option.name] = value;
  }
  return body;
}

export function WorkerOptionsFields({
  settings,
  mode,
  values,
  onChange,
}: {
  settings: WorkerSettings;
  mode: OptionsMode;
  values: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const options = optionsForMode(settings.declared_options ?? [], mode);
  if (options.length === 0) {
    return <p className="text-xs text-(--color-muted)">Este worker não declara opções além da engine e do lote.</p>;
  }

  const set = (name: string, value: unknown) => {
    const next = { ...values };
    if (value === undefined) delete next[name];
    else next[name] = value;
    onChange(next);
  };

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {options.map((option) => {
        const copy = labelOf(option);
        const value = values[option.name];
        if (option.kind === "boolean") {
          return (
            <label key={option.name} className="flex items-start gap-2 rounded-md bg-black/[0.02] px-3 py-2 text-xs">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={value === true}
                onChange={(event) => {
                  // A run sends the flag either way (unchecking turns off a persisted default); a
                  // settings row keeps only the true, because an absent key follows the code.
                  if (event.target.checked) set(option.name, true);
                  else if (mode === "run") set(option.name, false);
                  else set(option.name, undefined);
                }}
              />
              <span className="grid gap-0.5">
                <span>{copy.label}</span>
                <span className="font-mono text-[11px] text-(--color-muted)">{option.name}</span>
                {copy.hint ? <span className="text-(--color-muted)">{copy.hint}</span> : null}
              </span>
            </label>
          );
        }
        if (option.kind === "columns") {
          return (
            <Field
              key={option.name}
              className="sm:col-span-2"
              label={
                <>
                  {copy.label} <code className="font-mono text-[11px] text-(--color-muted)">{option.name}</code>
                </>
              }
              hint={copy.hint}
            >
              <div className="flex flex-wrap gap-x-4 gap-y-1 rounded-md bg-black/[0.02] px-3 py-2">
                {(option.choices ?? []).length === 0 ? (
                  <span className="text-(--color-muted)">O contrato não declara colunas para esta opção.</span>
                ) : null}
                {(option.choices ?? []).map((column) => {
                  const selected = Array.isArray(value) ? (value as string[]) : [];
                  return (
                    <label key={column} className="flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        checked={selected.includes(column)}
                        onChange={(event) => {
                          const next = event.target.checked
                            ? [...selected, column]
                            : selected.filter((item) => item !== column);
                          set(option.name, next.length > 0 ? next : undefined);
                        }}
                      />
                      <span className="font-mono text-[11px]">{column}</span>
                    </label>
                  );
                })}
              </div>
            </Field>
          );
        }
        if (option.kind === "list") {
          return (
            <Field key={option.name} label={copy.label} hint={copy.hint}>
              <Input
                value={Array.isArray(value) ? (value as string[]).join(", ") : ""}
                placeholder="separadas por vírgula"
                onChange={(event) => {
                  const parts = event.target.value
                    .split(",")
                    .map((part) => part.trim())
                    .filter(Boolean);
                  set(option.name, parts.length > 0 ? parts : undefined);
                }}
              />
            </Field>
          );
        }
        const numeric = option.kind === "integer" || option.kind === "number";
        return (
          <Field
            key={option.name}
            label={
              <>
                {copy.label} <code className="font-mono text-[11px] text-(--color-muted)">{option.name}</code>
              </>
            }
            hint={copy.hint}
          >
            <Input
              type={numeric ? "number" : "text"}
              step={option.kind === "number" ? "any" : undefined}
              value={value === undefined || value === null ? "" : String(value)}
              placeholder={option.default === null || option.default === undefined ? "o do código" : String(option.default)}
              onChange={(event) => {
                const text = event.target.value;
                if (text === "") {
                  set(option.name, undefined);
                  return;
                }
                set(option.name, numeric ? Number(text) : text);
              }}
            />
          </Field>
        );
      })}
    </div>
  );
}
