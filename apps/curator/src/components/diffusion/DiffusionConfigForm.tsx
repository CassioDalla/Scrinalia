import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  updateDiffusionChannel,
  type DiffusionChannel,
  type DiffusionConfigField,
} from "@/api/client";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input } from "@/components/ui/Input";
import { useCopy } from "@/i18n/context";
import { activeMessages } from "@/i18n/locale";

/**
 * **One** renderer over a channel's `config_fields`, never one component per channel.
 *
 * The channel's own Pydantic model is what the API validates; `config_fields` is metadata *about*
 * that model — the label, the help, the control kind — and this form is the only place it is read.
 * A channel that needs a bespoke control is a sign the metadata is insufficient, not a reason to
 * fork the page: the dataset adapter (#214) and any later channel arrive as registry entries with
 * their own fields, and the screen learns nothing.
 *
 * The three conversions are the whole contract, and each one exists for a measured reason:
 *
 * * **an empty text is sent as `null`, never as `""`.** `PublicSiteConfig.logo_url` is an `HttpUrl`,
 *   and `""` is not a URL: the API would answer 422 on a form the operator only cleared. `null`
 *   passes the optional field and `exclude_none` drops it from the stored JSONB.
 * * **a boolean is always sent**, because `false` is a decision (`allow_indexing`) and dropping it
 *   would silently re-enable the default.
 * * **a required field with no value disables the save**, so the operator sees the missing piece
 *   before the API has to refuse it.
 */

type Value = string | number | boolean;

/** The form's starting state: the saved value, the field default, or empty. */
export function initialConfig(
  fields: DiffusionConfigField[],
  values: Record<string, unknown>,
): Record<string, Value> {
  return Object.fromEntries(
    fields.map((field) => {
      const value = values[field.name] ?? field.default ?? "";
      if (field.kind === "boolean") return [field.name, Boolean(value)];
      if (field.kind === "number") return [field.name, typeof value === "number" ? value : String(value)];
      return [field.name, value == null ? "" : String(value)];
    }),
  );
}

/** The JSON the route validates, derived from the metadata and not typed per channel. */
export function configValues(
  fields: DiffusionConfigField[],
  values: Record<string, Value>,
): Record<string, unknown> {
  return Object.fromEntries(
    fields.map((field) => {
      const value = values[field.name];
      if (field.kind === "boolean") return [field.name, Boolean(value)];
      const text = String(value ?? "").trim();
      if (text === "") return [field.name, null];
      return [field.name, field.kind === "number" ? Number(text) : text];
    }),
  );
}

/** Whether a required text/number field is still empty; the save waits for it. */
export function missingRequired(
  fields: DiffusionConfigField[],
  values: Record<string, Value>,
): boolean {
  return fields.some(
    (field) => field.required && field.kind !== "boolean" && String(values[field.name] ?? "").trim() === "",
  );
}

/**
 * The effective configuration in one muted line, the same reading the origins page gives.
 *
 * It is rendered from `config_fields` too, so a field added to the channel's model and to the
 * registry appears in the summary without this file changing.
 */
export function configSummary(channel: DiffusionChannel): string {
  const messages = activeMessages().pages.diffusion;
  const config = channel.config ?? {};
  const parts = (channel.config_fields ?? []).flatMap((field) => {
    const value = config[field.name];
    if (value === null || value === undefined || value === "") return [];
    const rendered = typeof value === "boolean" ? (value ? messages.yes : messages.no) : String(value);
    return [`${field.label}: ${rendered}`];
  });
  return parts.length > 0 ? parts.join(" · ") : messages.noOwnConfig;
}

export function DiffusionConfigForm({
  channel,
  mode,
  onSaved,
}: {
  channel: DiffusionChannel;
  /** `create` is the add panel's gesture: the row is created enabled. `edit` keeps the lifecycle. */
  mode: "create" | "edit";
  onSaved?: (channel: DiffusionChannel) => void;
}) {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const fields = channel.config_fields ?? [];
  const [values, setValues] = useState<Record<string, Value>>(() =>
    initialConfig(fields, channel.config ?? {}),
  );

  const save = useMutation({
    mutationFn: () =>
      updateDiffusionChannel(channel.code, {
        // The lifecycle is not a field of this form: adding activates, editing leaves it alone.
        enabled: mode === "create" ? true : undefined,
        config: configValues(fields, values),
      }),
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ["diffusion", "channels"] });
      onSaved?.(saved);
    },
  });

  if (fields.length === 0) {
    return <p className="text-xs text-(--color-muted)">{messages.pages.diffusion.noConfigFields}</p>;
  }

  return (
    <div className="grid gap-3 rounded-md bg-black/[0.02] p-3 ring-1 ring-(--color-line)">
      <div className="grid gap-3 sm:grid-cols-2">
        {fields.map((field) => (
          <Field
            key={field.name}
            label={
              <>
                {field.label}
                {field.required ? (
                  <span className="text-(--color-muted)"> · {messages.pages.diffusion.required}</span>
                ) : null}
              </>
            }
            hint={field.help}
          >
            {field.kind === "boolean" ? (
              <input
                type="checkbox"
                className="size-4 accent-(--color-accent)"
                checked={Boolean(values[field.name])}
                onChange={(event) => setValues({ ...values, [field.name]: event.target.checked })}
              />
            ) : (
              <Input
                type={field.kind === "number" ? "number" : "text"}
                value={String(values[field.name] ?? "")}
                required={field.required}
                onChange={(event) => setValues({ ...values, [field.name]: event.target.value })}
              />
            )}
          </Field>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={save.isPending || missingRequired(fields, values)}
          onClick={() => save.mutate()}
        >
          {save.isPending
            ? messages.pages.diffusion.saving
            : mode === "create"
              ? messages.pages.diffusion.add
              : messages.pages.diffusion.saveConfig}
        </Button>
        {save.data ? (
          <span className="text-xs text-(--color-muted)">{messages.pages.diffusion.configSaved}</span>
        ) : null}
      </div>
      {save.error ? <ErrorState error={save.error} /> : null}
    </div>
  );
}
