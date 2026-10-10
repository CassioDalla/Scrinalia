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
            ? `${rows.length} níveis · ${formatCount(withDocuments)} descrições classificadas`
            : undefined
        }
      />

      <PageBody>
        <Notice tone="accent">
          A norma é o padrão, não a lei — mas ela é a assimetria que sustenta a carga: um nível
          desconhecido que chega da origem <strong>entra</strong> (a descrição fica sem nível e o
          diagnóstico a lista), enquanto o arquivista <strong>não</strong> pode salvar um nível que
          não existe. Sem isso, uma lote inteiro falharia por causa de uma grafia nova.
        </Notice>

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
      toggleLabel="Editar este nível"
      className={level.is_active ? undefined : "opacity-80"}
      header={
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="accent" title="Posição na escada; não é editável depois de criada">
            {level.ordinal}
          </Badge>
          <span className="text-sm font-medium">{level.name}</span>
          <code className="text-xs text-(--color-muted)">{level.code}</code>
          {level.is_active ? <Badge tone="ok">ativo</Badge> : <Badge tone="neutral">desativado</Badge>}
          <Badge tone="neutral" title="Descrições classificadas neste nível">
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
          <Field label="Nome">
            <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={60} />
          </Field>
          <Field label="Grafias aceitas (separadas por vírgula)">
            <Input
              value={aliases}
              onChange={(event) => setAliases(event.target.value)}
              placeholder="ex.: subsérie, sub-serie"
            />
          </Field>
        </div>

        <Field label="Descrição (o que o arquivista lê)">
          <Input value={description} onChange={(event) => setDescription(event.target.value)} />
        </Field>

        <div className="flex flex-wrap items-center gap-4 text-xs">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={requiresParent}
              onChange={(event) => setRequiresParent(event.target.checked)}
            />
            <span>exige unidade superior</span>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={allowsChildren}
              onChange={(event) => setAllowsChildren(event.target.checked)}
            />
            <span>pode ter filhos</span>
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
          {dirty ? <span className="text-xs text-(--color-muted)">alterações não salvas</span> : null}
        </div>
        {save.error ? <ErrorState error={save.error} /> : null}
      </div>
    </Disclosure>
  );
}

function CreateLevelCard({ onCreated }: { onCreated: () => void }) {
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
      triggerLabel="+ Novo degrau"
      toggleLabel="Acrescentar um degrau"
      header={
        <div className="grid gap-1">
          <span className="text-sm font-semibold">Acrescentar um degrau</span>
          <span className="text-xs text-(--color-muted)">
            Um ordinal novo e um código novo são um degrau novo; o ordinal não é editável depois.
          </span>
        </div>
      }
    >
      <div className="grid gap-2">
        <p className="text-xs text-(--color-muted)">
          O ordinal é a posição na escada: um nível só pode ser filho de outro de ordinal menor. Ele
          não é editável depois — mudá-lo renumeraria a árvore, e a árvore passada foi decidida contra
          estes números. Um ordinal novo e um código novo são um degrau novo.
        </p>
        <div className="grid gap-2 sm:grid-cols-4">
          <Field label="Ordinal">
            <Input
              type="number"
              min={0}
              value={draft.ordinal}
              onChange={(event) => setDraft({ ...draft, ordinal: Number(event.target.value) })}
            />
          </Field>
          <Field label="Código">
            <Input
              value={draft.code}
              onChange={(event) => setDraft({ ...draft, code: event.target.value })}
              placeholder="ex.: serie"
              maxLength={20}
            />
          </Field>
          <Field label="Nome">
            <Input
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder="ex.: Série"
              maxLength={60}
            />
          </Field>
          <Field label="Grafias aceitas">
            <Input value={aliases} onChange={(event) => setAliases(event.target.value)} />
          </Field>
        </div>
        <Field label="Descrição">
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
            <span>exige unidade superior</span>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.allows_children}
              onChange={(event) => setDraft({ ...draft, allows_children: event.target.checked })}
            />
            <span>pode ter filhos</span>
          </label>
        </div>
        <div>
          <Button variant="primary" disabled={!valid || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? ACTION.create.pending : `${ACTION.create.label} nível`}
          </Button>
        </div>
        {create.error ? <ErrorState error={create.error} /> : null}
      </div>
    </Disclosure>
  );
}
