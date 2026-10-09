import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createTypology,
  updateTypology,
  type Typology,
  type TypologyCreateRequest,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
import { ACTION } from "@/lib/copy";
import { descricoes, formatCount } from "@/lib/format";

/**
 * The catalogue of documental typologies — the diplomatic form of a record.
 *
 * Three things the API decided and the screen has to say rather than work around:
 *
 * * **there is no delete.** ``archive_documents.typology_id`` is ``SET NULL``, so removing a row
 *   would unclassify every description carrying it while erasing the record that the type ever
 *   existed. ``is_active=false`` is the way out, and it keeps the weight visible;
 * * **retiring is the only lever that reaches the classifier.** The zero-shot engine reads the
 *   active names as its candidate labels, so a retired type stops being proposed without a single
 *   classified description being touched — which is exactly why the weight stays on screen;
 * * **the context is documentation, not a prompt.** Appending it to the label makes the model lose
 *   the entailment as the label grows and collapse the collection onto one typology (measured on
 *   ``mDeBERTa-v3-base-mnli-xnli``). The field exists for the person reading the catalogue.
 */
export function TypologiesRoute() {
  const queryClient = useQueryClient();
  const catalog = useQuery(queries.typologyCatalog());

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["typologies"] });
    // The dossier's select reads the active subset: a typology that just changed must reach it.
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
  };

  const rows = catalog.data ?? [];
  const classified = rows.reduce((sum, row) => sum + (row.document_count ?? 0), 0);
  const active = rows.filter((row) => row.is_active).length;

  return (
    <>
      <PageHeader
        screen="typologies"
        pending={catalog.isPending}
        status={
          catalog.data
            ? `${rows.length} tipologias · ${active} ativas · ${formatCount(classified)} descrições classificadas`
            : undefined
        }
      />

      <div className="grid max-w-5xl gap-4 px-6 py-5">
        <p className="rounded-md bg-(--color-accent)/5 px-3 py-2 text-xs text-(--color-accent) ring-1 ring-(--color-accent)/20">
          O nome é o rótulo que o classificador propõe, e a descrição de contexto é{" "}
          <strong>documentação para quem lê o catálogo</strong> — ela nunca vai para o modelo.
          Aposentar uma tipologia a tira das opções do classificador <strong>sem</strong> desclassificar
          nenhuma descrição: por isso o peso de cada uma continua visível.
        </p>

        {catalog.error ? <ErrorState error={catalog.error} /> : null}
        {catalog.isPending ? (
          <div className="grid gap-2">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-16" />
            ))}
          </div>
        ) : null}

        {/* The write comes first, like the level ladder's: the form is about the list below it. */}
        <CreateTypologyCard onCreated={invalidate} />

        <section className="grid gap-2">
          {rows.map((typology) => (
            <TypologyCard key={typology.typology_id} typology={typology} onChanged={invalidate} />
          ))}
        </section>
      </div>
    </>
  );
}

function TypologyCard({ typology, onChanged }: { typology: Typology; onChanged: () => void }) {
  const [name, setName] = useState(typology.name);
  const [context, setContext] = useState(typology.context_description ?? "");

  const save = useMutation({
    mutationFn: (changes: {
      name?: string;
      context_description?: string | null;
      is_active?: boolean;
    }) => updateTypology(typology.typology_id, changes),
    onSuccess: onChanged,
  });

  const dirty = name !== typology.name || context !== (typology.context_description ?? "");

  return (
    <Disclosure
      toggleLabel="Editar esta tipologia"
      className={typology.is_active ? undefined : "opacity-80"}
      header={
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{typology.name}</span>
          {typology.is_active ? <Badge tone="ok">ativa</Badge> : <Badge tone="neutral">aposentada</Badge>}
          <Badge tone="neutral" title="Descrições classificadas com esta tipologia">
            {descricoes(typology.document_count ?? 0)}
          </Badge>
          {typology.context_description ? (
            <span className="w-full text-xs text-(--color-muted)">{typology.context_description}</span>
          ) : null}
        </div>
      }
      actions={
        <Button
          size="sm"
          variant={typology.is_active ? "ghost" : "secondary"}
          disabled={save.isPending}
          title={
            typology.is_active
              ? "Sai das opções do classificador; as descrições já classificadas mantêm a tipologia."
              : "Volta a ser uma opção do classificador."
          }
          onClick={() => save.mutate({ is_active: !typology.is_active })}
        >
          {typology.is_active ? ACTION.retire.label : ACTION.reactivate.label}
        </Button>
      }
    >
      <div className="grid gap-2">
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Nome (o rótulo do classificador)</span>
          <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} />
        </label>

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">
            Descrição de contexto (o que cai nesta tipologia; o arquivista lê, o modelo não)
          </span>
          <Input value={context} onChange={(event) => setContext(event.target.value)} />
        </label>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="primary"
            disabled={!dirty || save.isPending || name.trim().length === 0}
            onClick={() =>
              save.mutate({
                name: name.trim(),
                context_description: context.trim() || null,
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

function CreateTypologyCard({ onCreated }: { onCreated: () => void }) {
  const empty: TypologyCreateRequest = { name: "", context_description: null };
  const [draft, setDraft] = useState<TypologyCreateRequest>(empty);

  const create = useMutation({
    mutationFn: () => createTypology(draft),
    onSuccess: () => {
      setDraft(empty);
      onCreated();
    },
  });

  const valid = draft.name.trim().length > 0;

  return (
    <Disclosure
      triggerLabel="+ Nova tipologia"
      toggleLabel="Criar uma tipologia"
      header={
        <div className="grid gap-1">
          <span className="text-sm font-semibold">Criar uma tipologia</span>
          <span className="text-xs text-(--color-muted)">
            Vale a pena quando o acervo carrega uma forma que o classificador não tem como propor —
            e o nome é o rótulo que ele vai usar.
          </span>
        </div>
      }
    >
      <div className="grid gap-2">
        <p className="text-xs text-(--color-muted)">
          O classificador recebe <strong>só o nome</strong>. Um nome comprido ou uma frase fazem o
          modelo perder o vínculo com o texto e rotular tudo com a mesma tipologia, então prefira a
          forma diplomática curta (Ata de Reunião, Ofício, Planta) e deixe os exemplos na descrição de
          contexto.
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Nome</span>
            <Input
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder="ex.: Ata de Reunião"
              maxLength={100}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Descrição de contexto</span>
            <Input
              value={draft.context_description ?? ""}
              onChange={(event) => setDraft({ ...draft, context_description: event.target.value || null })}
              placeholder="ex.: registros de encontros e deliberações"
            />
          </label>
        </div>
        <div>
          <Button
            variant="primary"
            disabled={!valid || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? ACTION.create.pending : `${ACTION.create.label} tipologia`}
          </Button>
        </div>
        {create.error ? <ErrorState error={create.error} /> : null}
      </div>
    </Disclosure>
  );
}
