import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createLevel,
  updateLevel,
  type DescriptionLevel,
  type DescriptionLevelCreateRequest,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { ACTION } from "@/lib/copy";
import { descricoes, formatCount } from "@/lib/format";
import { useCopy } from "@/i18n/context";

/**
 * The ladder the arrangement is written against.
 *
 * Three things the API decided and the screen has to say rather than work around:
 *
 * * **there is no delete.** The level's FK is ``SET NULL``, so deleting a rung would erase the fact
 *   that it existed and silently orphan the descriptions sitting on it. ``is_active=false`` is the
 *   way out, and it keeps the weight visible;
 * * **``ordinal`` is not editable.** Re-ranking a ladder would renumber the tree the past decided
 *   against; the route does not accept the field, so the screen does not offer it. A wrong ordinal
 *   is a new rung, not a rename;
 * * **the load tolerates an unknown level, the archivist does not.** That asymmetry is deliberate:
 *   a batch must never fail because the source carried a rung this catalog does not know, and a
 *   human editing a description must not be allowed to invent one.
 */
export function LevelsRoute() {
  const messages = useCopy();
  const queryClient = useQueryClient();
  const levels = useQuery(queries.levelCatalog());

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["hierarchy", "levels"] });
    // The dossier's selects read the active subset: a rung that just changed must reach them.
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
  };

  const rows = [...(levels.data ?? [])].sort((a, b) => a.ordinal - b.ordinal);
  const withDocuments = rows.reduce((sum, row) => sum + (row.document_count ?? 0), 0);

  return (
    <>
      <PageHeader
        screen="levels"
        pending={levels.isPending}
        status={
          levels.data
            ? messages.pages.levels.status
                .replace("{levels}", String(rows.length))
                .replace("{documents}", formatCount(withDocuments))
            : undefined
        }
      />

      <PageBody>
        <Notice tone="accent">{messages.pages.levels.normNotice}</Notice>

        {levels.error ? <ErrorState error={levels.error} /> : null}
        {levels.isPending ? (
          <div className="grid gap-2">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-20" />
            ))}
          </div>
        ) : null}

        {/*
          The write comes first, the catalogue second.
          
          The card used to sit at the bottom: on a ladder of a dozen rungs the archivist had to scroll
          past everything they were comparing against to find the button — and the ordinal rule ("um
          nível só pode ser filho de outro de ordinal menor") is exactly the kind of decision that
          needs the ladder visible while filling the form. Hence a disclosure and not a modal: a popup
          would cover the very thing the form is about.
        */}
        <CreateLevelCard onCreated={invalidate} />

        <section className="grid gap-2">
          {rows.map((level) => (
            <LevelCard key={level.level_id} level={level} onChanged={invalidate} />
          ))}
        </section>
      </PageBody>
    </>
  );
}

function LevelCard({ level, onChanged }: { level: DescriptionLevel; onChanged: () => void }) {
  const messages = useCopy();
  const [name, setName] = useState(level.name);
  const [description, setDescription] = useState(level.description ?? "");
  const [aliases, setAliases] = useState((level.aliases ?? []).join(", "));
  const [requiresParent, setRequiresParent] = useState(level.requires_parent);
  const [allowsChildren, setAllowsChildren] = useState(level.allows_children);

  const save = useMutation({
    mutationFn: (changes: {
      name?: string;
      description?: string | null;
      aliases?: string[];
      requires_parent?: boolean;
      allows_children?: boolean;
      is_active?: boolean;
    }) => updateLevel(level.level_id, changes),
    onSuccess: onChanged,
  });

  const dirty =
    name !== level.name ||
    description !== (level.description ?? "") ||
    aliases !== (level.aliases ?? []).join(", ") ||
    requiresParent !== level.requires_parent ||
    allowsChildren !== level.allows_children;

  return (
    <Disclosure
      toggleLabel={messages.pages.levels.editToggle}
      className={level.is_active ? undefined : "opacity-80"}
      header={
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="accent" title={messages.pages.levels.ordinalTitle}>
            {level.ordinal}
          </Badge>
          <span className="text-sm font-medium">{level.name}</span>
          <code className="text-xs text-(--color-muted)">{level.code}</code>
          {level.is_active ? (
            <Badge tone="ok">{messages.pages.levels.activeBadge}</Badge>
          ) : (
            <Badge tone="neutral">{messages.pages.levels.retiredBadge}</Badge>
          )}
          <Badge tone="neutral" title={messages.pages.levels.documentsBadgeTitle}>
            {descricoes(level.document_count ?? 0)}
          </Badge>
          {level.description ? (
            <span className="w-full text-xs text-(--color-muted)">{level.description}</span>
          ) : null}
        </div>
      }
      actions={
        <Button
          size="sm"
          variant={level.is_active ? "ghost" : "secondary"}
          disabled={save.isPending}
          onClick={() => save.mutate({ is_active: !level.is_active })}
        >
          {level.is_active ? ACTION.retire.label : ACTION.reactivate.label}
        </Button>
      }
    >
      <div className="grid gap-2">
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label={messages.pages.levels.nameField}>
            <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={60} />
          </Field>
          <Field label={messages.pages.levels.aliasesField}>
            <Input
              value={aliases}
              onChange={(event) => setAliases(event.target.value)}
              placeholder={messages.pages.levels.aliasesPlaceholder}
            />
          </Field>
        </div>

        <Field label={messages.pages.levels.descriptionField}>
          <Input value={description} onChange={(event) => setDescription(event.target.value)} />
        </Field>

        <div className="flex flex-wrap items-center gap-4 text-xs">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={requiresParent}
              onChange={(event) => setRequiresParent(event.target.checked)}
            />
            <span>{messages.pages.levels.requiresParent}</span>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={allowsChildren}
              onChange={(event) => setAllowsChildren(event.target.checked)}
            />
            <span>{messages.pages.levels.allowsChildren}</span>
          </label>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="primary"
            disabled={!dirty || save.isPending || name.trim().length === 0}
            onClick={() =>
              save.mutate({
                name: name.trim(),
                description: description.trim() || null,
                aliases: aliases
                  .split(",")
                  .map((value) => value.trim())
                  .filter(Boolean),
                requires_parent: requiresParent,
                allows_children: allowsChildren,
              })
            }
          >
            {save.isPending ? ACTION.save.pending : ACTION.save.label}
          </Button>
          {dirty ? <span className="text-xs text-(--color-muted)">{messages.pages.levels.unsaved}</span> : null}
        </div>
        {save.error ? <ErrorState error={save.error} /> : null}
      </div>
    </Disclosure>
  );
}

function CreateLevelCard({ onCreated }: { onCreated: () => void }) {
  const messages = useCopy();
  const empty: DescriptionLevelCreateRequest = {
    ordinal: 0,
    code: "",
    name: "",
    description: null,
    aliases: [],
    requires_parent: false,
    allows_children: true,
  };
  const [draft, setDraft] = useState<DescriptionLevelCreateRequest>(empty);
  const [aliases, setAliases] = useState("");

  const create = useMutation({
    mutationFn: () => createLevel({ ...draft, aliases: aliases.split(",").map((v) => v.trim()).filter(Boolean) }),
    onSuccess: () => {
      setDraft(empty);
      setAliases("");
      onCreated();
    },
  });

  const valid = draft.code.trim().length > 0 && draft.name.trim().length > 0;

  return (
    <Disclosure
      triggerLabel={messages.pages.levels.newRung}
      toggleLabel={messages.pages.levels.addRung}
      header={
        <div className="grid gap-1">
          <span className="text-sm font-semibold">{messages.pages.levels.addRung}</span>
          <span className="text-xs text-(--color-muted)">{messages.pages.levels.ordinalFixed}</span>
        </div>
      }
    >
      <div className="grid gap-2">
        <p className="text-xs text-(--color-muted)">{messages.pages.levels.ordinalExplanation}</p>
        <div className="grid gap-2 sm:grid-cols-4">
          <Field label={messages.pages.levels.ordinalField}>
            <Input
              type="number"
              min={0}
              value={draft.ordinal}
              onChange={(event) => setDraft({ ...draft, ordinal: Number(event.target.value) })}
            />
          </Field>
          <Field label={messages.pages.levels.codeField}>
            <Input
              value={draft.code}
              onChange={(event) => setDraft({ ...draft, code: event.target.value })}
              placeholder={messages.pages.levels.codePlaceholder}
              maxLength={20}
            />
          </Field>
          <Field label="Nome">
            <Input
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder={messages.pages.levels.namePlaceholder}
              maxLength={60}
            />
          </Field>
          <Field label={messages.pages.levels.aliasesFieldShort}>
            <Input value={aliases} onChange={(event) => setAliases(event.target.value)} />
          </Field>
        </div>
        <Field label={messages.pages.levels.descriptionFieldShort}>
          <Input
            value={draft.description ?? ""}
            onChange={(event) => setDraft({ ...draft, description: event.target.value || null })}
          />
        </Field>
        <div className="flex flex-wrap items-center gap-4 text-xs">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.requires_parent}
              onChange={(event) => setDraft({ ...draft, requires_parent: event.target.checked })}
            />
            <span>{messages.pages.levels.requiresParent}</span>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.allows_children}
              onChange={(event) => setDraft({ ...draft, allows_children: event.target.checked })}
            />
            <span>{messages.pages.levels.allowsChildren}</span>
          </label>
        </div>
        <div>
          <Button variant="primary" disabled={!valid || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? ACTION.create.pending : messages.pages.levels.createLevel}
          </Button>
        </div>
        {create.error ? <ErrorState error={create.error} /> : null}
      </div>
    </Disclosure>
  );
}
