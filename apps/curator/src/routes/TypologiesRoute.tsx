import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import {
  createTypology,
  updateDocument,
  updateTypology,
  type Typology,
  type TypologyCreateRequest,
  type TypologyRefusalRow,
} from "@/api/client";
import { queries, TYPOLOGY_REFUSALS_PAGE_SIZE } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { SectionTitle } from "@/components/ui/SectionTitle";
import { ACTION } from "@/lib/copy";
import { descricoes, formatCount, formatDate } from "@/lib/format";
import { asNumber } from "@/lib/search";

const routeApi = getRouteApi("/arranjo/tipologias");

export type TypologiesSearch = { offset?: number };

/** The refusal queue is paged through the URL, like every other list in the SPA. */
export function validateTypologiesSearch(search: Record<string, unknown>): TypologiesSearch {
  const offset = asNumber(search.offset);
  return { offset: offset !== undefined && offset > 0 ? offset : undefined };
}

/**
 * The catalogue of documental typologies — the diplomatic form of a record — and the descriptions
 * the classifier refused to place.
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
 *
 * The refusal queue is the other half of the catalogue's meaning: ``typology_id`` NULL cannot say
 * whether the classifier declined or never reached a description, so the queue row is the evidence,
 * and the page is where the archivist settles it. The write is the dossier's own
 * ``PATCH /documents/{id}``; this screen does not invent a second command.
 */
export function TypologiesRoute() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const search = routeApi.useSearch();
  const offset = search.offset ?? 0;

  const catalog = useQuery(queries.typologyCatalog());
  const refusals = useQuery(queries.typologyRefusals(offset));

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["typologies"] });
    // The dossier's select reads the active subset: a typology that just changed must reach it.
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    // The home screen counts the same predicate the section just answered.
    void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
  };

  const rows = catalog.data ?? [];
  const activeRows = rows.filter((row) => row.is_active);
  const classified = rows.reduce((sum, row) => sum + (row.document_count ?? 0), 0);
  const refusalTotal = refusals.data?.total ?? 0;

  const onFiled = () => {
    invalidate();
    // Filing the only row of a page that is not the first would leave an empty page over a queue
    // that still has work: step back one page instead of showing "nothing pending" under a total.
    if ((refusals.data?.items?.length ?? 0) === 1 && offset > 0) {
      navigate({
        to: "/arranjo/tipologias",
        search: { offset: Math.max(0, offset - TYPOLOGY_REFUSALS_PAGE_SIZE) || undefined },
      });
    }
  };

  return (
    <>
      <PageHeader
        screen="typologies"
        pending={catalog.isPending || refusals.isPending}
        status={
          catalog.data
            ? `${rows.length} tipologias · ${activeRows.length} ativas · ${formatCount(classified)} descrições classificadas`
            : undefined
        }
      />

      <PageBody>
        <RefusalQueue
          rows={refusals.data?.items ?? []}
          total={refusalTotal}
          offset={offset}
          active={activeRows}
          catalog={rows}
          pending={refusals.isPending}
          error={refusals.error}
          onFiled={onFiled}
        />

        <SectionTitle>Catálogo</SectionTitle>

        <Notice tone="accent">
          O nome é o rótulo que o classificador propõe; a descrição de contexto é{" "}
          <strong>documentação para quem lê o catálogo</strong> e não chega à classificação.
          Aposentar uma tipologia a retira das opções do classificador <strong>sem</strong> desclassificar
          nenhuma descrição — por isso a contagem de cada uma continua visível.
        </Notice>

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
      </PageBody>
    </>
  );
}

/** The refused descriptions, the nearest miss first; the section that makes the queue actionable. */
function RefusalQueue({
  rows,
  total,
  offset,
  active,
  catalog,
  pending,
  error,
  onFiled,
}: {
  rows: TypologyRefusalRow[];
  total: number;
  offset: number;
  active: Typology[];
  catalog: Typology[];
  pending: boolean;
  error: unknown;
  onFiled: () => void;
}) {
  const navigate = useNavigate();

  return (
    <section className="grid gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <SectionTitle>Recusas do classificador</SectionTitle>
        {total > 0 ? (
          <span className="text-xs text-(--color-muted)">{descricoes(total)} aguardando tipologia</span>
        ) : null}
      </div>

      <p className="max-w-prose text-xs text-(--color-muted)">
        O classificador examinou estas descrições e não teve confiança suficiente para escolher uma
        tipologia. As que chegaram mais perto de ser classificadas vêm primeiro. Classificar aqui salva
        a escolha, registra a revisão e marca a descrição como aprovada por uma pessoa — o classificador
        não a altera depois. Se nenhuma tipologia serve, crie ou reative uma no catálogo abaixo.
      </p>

      {error ? <ErrorState error={error} /> : null}

      {pending && rows.length === 0 ? <Skeleton className="h-20" /> : null}

      {!pending && !error && total === 0 ? (
        <EmptyState
          title="Nenhuma recusa pendente"
          hint={
            <>
              Isso não quer dizer que o catálogo cobre o acervo: quer dizer que nenhuma descrição tem
              uma recusa aberta do classificador. Uma descrição que já recebeu tipologia sai daqui, e
              uma que o classificador nunca examinou não entra — a recusa só é registrada quando a
              classificação é feita e fica abaixo da confiança mínima.
            </>
          }
        />
      ) : null}

      {total > 0 ? (
        <div className="grid gap-2">
          {rows.map((row) => (
            <RefusalCard
              key={row.description_id}
              row={row}
              active={active}
              catalog={catalog}
              onFiled={onFiled}
            />
          ))}

          {total > TYPOLOGY_REFUSALS_PAGE_SIZE ? (
            <div className="flex items-center justify-between text-sm">
              <Button
                size="sm"
                disabled={offset === 0}
                onClick={() =>
                  navigate({
                    to: "/arranjo/tipologias",
                    search: {
                      offset: Math.max(0, offset - TYPOLOGY_REFUSALS_PAGE_SIZE) || undefined,
                    },
                  })
                }
              >
                ← Anterior
              </Button>
              <span className="text-xs text-(--color-muted)">
                {formatCount(offset + 1)}–{formatCount(Math.min(offset + TYPOLOGY_REFUSALS_PAGE_SIZE, total))} de{" "}
                {formatCount(total)}
              </span>
              <Button
                size="sm"
                disabled={offset + TYPOLOGY_REFUSALS_PAGE_SIZE >= total}
                onClick={() =>
                  navigate({
                    to: "/arranjo/tipologias",
                    search: { offset: offset + TYPOLOGY_REFUSALS_PAGE_SIZE },
                  })
                }
              >
                Próxima →
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

/** One refused description: the evidence, the choice and the dossier, in that order. */
function RefusalCard({
  row,
  active,
  catalog,
  onFiled,
}: {
  row: TypologyRefusalRow;
  active: Typology[];
  catalog: Typology[];
  onFiled: () => void;
}) {
  const [choice, setChoice] = useState("");
  const file = useMutation({
    mutationFn: (typologyId: number) => updateDocument(row.description_id, { typology_id: typologyId }),
    onSuccess: () => {
      setChoice("");
      onFiled();
    },
  });

  const title = row.final_title || row.original_title;
  const guessed = row.guessed_label ? catalog.find((typology) => typology.name === row.guessed_label) : undefined;
  const guessedRetired = guessed !== undefined && !guessed.is_active;
  const score = row.ai_confidence_score;

  return (
    <Card>
      <CardBody className="grid gap-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <Link
            to="/acervo/$descriptionId"
            params={{ descriptionId: row.description_id }}
            className="min-w-0 text-sm font-medium hover:underline"
          >
            {title}
          </Link>
          <Badge
            tone={score === null || score === undefined ? "neutral" : "warn"}
            title="A confiança que o classificador teve antes de recusar. Abaixo da confiança mínima, a decisão é sua."
          >
            {score === null || score === undefined ? "sem confiança registrada" : `confiança ${score.toFixed(2)}`}
          </Badge>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-(--color-muted)">
          {row.reference_code ? <code className="rounded bg-black/[0.05] px-1">{row.reference_code}</code> : null}
          <span>{formatDate(row.document_date)}</span>
          {row.guessed_label ? (
            <span>
              palpite: <strong className="font-medium">{row.guessed_label}</strong>
              {guessedRetired ? " (aposentada)" : ""}
            </span>
          ) : (
            <span>sem palpite registrado</span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Select
            className="w-64"
            aria-label={`Tipologia de ${title}`}
            value={choice}
            disabled={file.isPending}
            onChange={(event) => setChoice(event.target.value)}
          >
            <option value="">Escolha uma tipologia…</option>
            {active.map((typology) => (
              <option key={typology.typology_id} value={typology.typology_id}>
                {typology.name}
              </option>
            ))}
          </Select>
          <Button
            size="sm"
            variant="primary"
            disabled={!choice || file.isPending}
            onClick={() => file.mutate(Number(choice))}
          >
            {file.isPending ? "Classificando…" : "Classificar"}
          </Button>
          <Link to="/acervo/$descriptionId" params={{ descriptionId: row.description_id }}>
            <Button size="sm" variant="ghost">
              Abrir ficha
            </Button>
          </Link>
        </div>

        {file.error ? <ErrorState error={file.error} /> : null}
      </CardBody>
    </Card>
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
        <Field label="Nome (o rótulo do classificador)">
          <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={100} />
        </Field>

        <Field label="Descrição de Contexto (o que entra nesta tipologia; só o arquivista lê)">
          <Input value={context} onChange={(event) => setContext(event.target.value)} />
        </Field>

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
            Serve quando o acervo tem uma forma documental que o classificador não propõe; o nome é o
            rótulo que ele usa.
          </span>
        </div>
      }
    >
      <div className="grid gap-2">
        <p className="text-xs text-(--color-muted)">
          O classificador recebe <strong>só o nome</strong>. Um nome comprido ou uma frase fazem a
          classificação perder o vínculo com o texto e rotular tudo com a mesma tipologia: prefira a
          forma diplomática curta (Ata de Reunião, Ofício, Planta) e deixe os exemplos na descrição de
          contexto.
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Nome">
            <Input
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder="ex.: Ata de Reunião"
              maxLength={100}
            />
          </Field>
          <Field label="Descrição de Contexto">
            <Input
              value={draft.context_description ?? ""}
              onChange={(event) => setDraft({ ...draft, context_description: event.target.value || null })}
              placeholder="ex.: registros de encontros e deliberações"
            />
          </Field>
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
