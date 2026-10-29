import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createArrangementTerm,
  createCollectionTerm,
  updateArrangementTerm,
  updateCollectionTerm,
  type ArrangementTerm,
  type ArrangementTermCreateRequest,
  type CollectionTerm,
  type CollectionTermCreateRequest,
  type CollectionTermKind,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { PageBody } from "@/components/layout/PageBody";
import { SectionTitle } from "@/components/ui/SectionTitle";
import { ACTION } from "@/lib/copy";
import { formatCount } from "@/lib/format";
import { TERM_KIND_HINT, TERM_KIND_TONE, termKindLabel } from "@/lib/vocabulary";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";

/**
 * What *this* collection declares, as opposed to what the software or the language fixes.
 *
 * The distinction is the reason the screen exists. Everything the subject guard refuses falls into
 * two families, and only one of them is the archivist's to edit:
 *
 * * the **language** — ``rua``, ``não identificado``, ``303 anos``, a bare year — is Portuguese and
 *   lives in the language profile. It is not a curation decision, and offering it here would invite
 *   the archivist to change what the software means by a word;
 * * the **collection** — the bairros it names, the people it depicts, the tokens its reference codes
 *   carry — is a statement about this archive, and another institution's collection has other names.
 *   That is what this screen edits.
 *
 * There is no delete, for the same reason the other catalogues have none: removing an arrangement
 * name would make the proposal suggest nothing again, and removing a collection term would make a
 * term the archivist refused come back into the subject axis. ``is_active=false`` retires the row
 * and keeps the record that it existed.
 */
export function VocabularyRoute() {
  const messages = useCopy();
  const vocabulary = useQuery(queries.collectionVocabulary());

  const arrangement = vocabulary.data?.arrangement_terms ?? [];
  const terms = vocabulary.data?.collection_terms ?? [];
  const kinds = vocabulary.data?.kinds ?? [];
  const active = terms.filter((term) => term.is_active).length;

  return (
    <>
      <PageHeader
        screen="vocabulary"
        pending={vocabulary.isPending}
        status={
          vocabulary.data
            ? fill(messages.pages.vocabulary.status, {
                arrangement: String(arrangement.length),
                terms: String(terms.length),
                active: String(active),
              })
            : undefined
        }
      />

      <PageBody>
        <Notice tone="accent">{messages.pages.vocabulary.notice}</Notice>

        {vocabulary.error ? <ErrorState error={vocabulary.error} /> : null}
        {vocabulary.isPending ? (
          <div className="grid gap-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="h-16" />
            ))}
          </div>
        ) : null}

        <section className="grid gap-2">
          <SectionTitle>{messages.pages.vocabulary.arrangementSection}</SectionTitle>
          <p className="text-xs text-(--color-muted)">{messages.pages.vocabulary.arrangementHint}</p>
          <CreateArrangementTermCard />
          {arrangement.map((term) => (
            <ArrangementTermCard key={term.term_id} term={term} />
          ))}
        </section>

        <section className="grid gap-2">
          <SectionTitle>{messages.pages.vocabulary.collectionSection}</SectionTitle>
          <p className="text-xs text-(--color-muted)">{messages.pages.vocabulary.collectionHint}</p>
          <CreateCollectionTermCard kinds={kinds} />
          {terms.map((term) => (
            <CollectionTermCard key={term.term_id} term={term} kinds={kinds} />
          ))}
        </section>
      </PageBody>
    </>
  );
}

function useVocabularyInvalidation() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: ["vocabulary"] });
  };
}

function ArrangementTermCard({ term }: { term: ArrangementTerm }) {
  const messages = useCopy();
  const invalidate = useVocabularyInvalidation();
  const [displayName, setDisplayName] = useState(term.display_name);

  const save = useMutation({
    mutationFn: (changes: { display_name?: string; is_active?: boolean }) =>
      updateArrangementTerm(term.term_id, changes),
    onSuccess: invalidate,
  });

  const dirty = displayName !== term.display_name;

  return (
    <Disclosure
      toggleLabel={messages.pages.vocabulary.editName}
      className={term.is_active ? undefined : "opacity-80"}
      header={
        <div className="flex flex-wrap items-center gap-2">
          <code className="rounded bg-black/[0.05] px-1.5 py-0.5 text-xs">{term.token}</code>
          <span className="text-sm font-medium">{term.display_name}</span>
          {term.is_active ? (
              <Badge tone="ok">{messages.pages.categories.activeBadge}</Badge>
            ) : (
              <Badge tone="neutral">{messages.pages.categories.retiredBadge}</Badge>
            )}
        </div>
      }
      actions={
        <Button
          size="sm"
          variant={term.is_active ? "ghost" : "secondary"}
          disabled={save.isPending}
          title={
            term.is_active
              ? messages.pages.vocabulary.retireName
              : messages.pages.vocabulary.reactivateName
          }
          onClick={() => save.mutate({ is_active: !term.is_active })}
        >
          {term.is_active ? ACTION.retire.label : ACTION.reactivate.label}
        </Button>
      }
    >
      <div className="grid gap-2">
        <Field label={messages.pages.vocabulary.suggestedName}>
          <Input
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            maxLength={200}
          />
        </Field>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="primary"
            disabled={!dirty || save.isPending || displayName.trim().length === 0}
            onClick={() => save.mutate({ display_name: displayName.trim() })}
          >
            {save.isPending ? ACTION.save.pending : ACTION.save.label}
          </Button>
          {dirty ? <span className="text-xs text-(--color-muted)">{messages.pages.vocabulary.unsaved}</span> : null}
        </div>
        {save.error ? <ErrorState error={save.error} /> : null}
      </div>
    </Disclosure>
  );
}

function CreateArrangementTermCard() {
  const messages = useCopy();
  const invalidate = useVocabularyInvalidation();
  const empty: ArrangementTermCreateRequest = { token: "", display_name: "" };
  const [draft, setDraft] = useState<ArrangementTermCreateRequest>(empty);

  const create = useMutation({
    mutationFn: () => createArrangementTerm(draft),
    onSuccess: () => {
      setDraft(empty);
      invalidate();
    },
  });

  const valid = draft.token.trim().length > 0 && draft.display_name.trim().length > 0;

  return (
    <Disclosure
      triggerLabel={messages.pages.vocabulary.newName}
      triggerCloseLabel={messages.common.close}
      toggleLabel={messages.pages.vocabulary.createArrangement}
      header={
        <div className="grid gap-1">
          <span className="text-sm font-semibold">{messages.pages.vocabulary.createArrangement}</span>
          <span className="text-xs text-(--color-muted)">{messages.pages.vocabulary.segmentHint}</span>
        </div>
      }
    >
      <div className="grid gap-2">
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label={messages.pages.vocabulary.segmentField}>
            <Input
              value={draft.token}
              onChange={(event) => setDraft({ ...draft, token: event.target.value })}
              placeholder={messages.pages.vocabulary.segmentPlaceholder}
              maxLength={100}
            />
          </Field>
          <Field label="Nome Sugerido">
            <Input
              value={draft.display_name}
              onChange={(event) => setDraft({ ...draft, display_name: event.target.value })}
              placeholder={messages.pages.vocabulary.namePlaceholder}
              maxLength={200}
            />
          </Field>
        </div>
        <div>
          <Button variant="primary" disabled={!valid || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? ACTION.create.pending : messages.pages.vocabulary.createNameButton}
          </Button>
        </div>
        {create.error ? <ErrorState error={create.error} /> : null}
      </div>
    </Disclosure>
  );
}

function CollectionTermCard({ term, kinds }: { term: CollectionTerm; kinds: CollectionTermKind[] }) {
  const messages = useCopy();
  const invalidate = useVocabularyInvalidation();
  const [spelling, setSpelling] = useState(term.term);
  const [kind, setKind] = useState<CollectionTermKind>(term.kind);

  const save = useMutation({
    mutationFn: (changes: { term?: string; kind?: CollectionTermKind; is_active?: boolean }) =>
      updateCollectionTerm(term.term_id, changes),
    onSuccess: invalidate,
  });

  const dirty = spelling !== term.term || kind !== term.kind;

  return (
    <Disclosure
      toggleLabel={messages.pages.vocabulary.editTerm}
      className={term.is_active ? undefined : "opacity-80"}
      header={
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{term.term}</span>
          <Badge tone={TERM_KIND_TONE[term.kind] ?? "neutral"}>{termKindLabel(term.kind)}</Badge>
          {term.is_active ? <Badge tone="ok">ativo</Badge> : <Badge tone="neutral">aposentado</Badge>}
          <Badge tone="neutral" title={messages.pages.vocabulary.tagsBadgeTitle}>
            {formatCount(term.tag_count ?? 0)} tags
          </Badge>
        </div>
      }
      actions={
        <Button
          size="sm"
          variant={term.is_active ? "ghost" : "secondary"}
          disabled={save.isPending}
          title={
            term.is_active
              ? messages.pages.vocabulary.retireTerm
              : messages.pages.vocabulary.reactivateTerm
          }
          onClick={() => save.mutate({ is_active: !term.is_active })}
        >
          {term.is_active ? ACTION.retire.label : ACTION.reactivate.label}
        </Button>
      }
    >
      <div className="grid gap-2">
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label={messages.pages.vocabulary.spellingField}>
            <Input
              value={spelling}
              onChange={(event) => setSpelling(event.target.value)}
              maxLength={200}
            />
          </Field>
          <Field label={messages.pages.vocabulary.kindField}>
            <Select
              value={kind}
              onChange={(event) => setKind(event.target.value as CollectionTermKind)}
            >
              {kinds.map((option) => (
                <option key={option} value={option}>
                  {termKindLabel(option)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <p className="text-xs text-(--color-muted)">{TERM_KIND_HINT[kind] ?? ""}</p>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="primary"
            disabled={!dirty || save.isPending || spelling.trim().length === 0}
            onClick={() => save.mutate({ term: spelling.trim(), kind })}
          >
            {save.isPending ? ACTION.save.pending : ACTION.save.label}
          </Button>
          {dirty ? <span className="text-xs text-(--color-muted)">{messages.pages.vocabulary.unsaved}</span> : null}
        </div>
        {save.error ? <ErrorState error={save.error} /> : null}
      </div>
    </Disclosure>
  );
}

function CreateCollectionTermCard({ kinds }: { kinds: CollectionTermKind[] }) {
  const messages = useCopy();
  const invalidate = useVocabularyInvalidation();
  const empty: CollectionTermCreateRequest = { term: "", kind: "DISTRICT" };
  const [draft, setDraft] = useState<CollectionTermCreateRequest>(empty);

  const create = useMutation({
    mutationFn: () => createCollectionTerm(draft),
    onSuccess: () => {
      setDraft(empty);
      invalidate();
    },
  });

  const valid = draft.term.trim().length > 0;

  return (
    <Disclosure
      triggerLabel={messages.pages.vocabulary.newTerm}
      triggerCloseLabel="fechar"
      toggleLabel={messages.pages.vocabulary.createCollectionTerm}
      header={
        <div className="grid gap-1">
          <span className="text-sm font-semibold">{messages.pages.vocabulary.createCollectionTerm}</span>
          <span className="text-xs text-(--color-muted)">{messages.pages.vocabulary.termHint}</span>
        </div>
      }
    >
      <div className="grid gap-2">
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label={messages.pages.vocabulary.spellingFieldShort}>
            <Input
              value={draft.term}
              onChange={(event) => setDraft({ ...draft, term: event.target.value })}
              placeholder={messages.pages.vocabulary.spellingPlaceholder}
              maxLength={200}
            />
          </Field>
          <Field label="Tipo">
            <Select
              value={draft.kind}
              onChange={(event) => setDraft({ ...draft, kind: event.target.value as CollectionTermKind })}
            >
              {kinds.map((option) => (
                <option key={option} value={option}>
                  {termKindLabel(option)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <p className="text-xs text-(--color-muted)">{TERM_KIND_HINT[draft.kind] ?? ""}</p>
        <div>
          <Button variant="primary" disabled={!valid || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? ACTION.create.pending : messages.pages.vocabulary.createTermButton}
          </Button>
        </div>
        {create.error ? <ErrorState error={create.error} /> : null}
      </div>
    </Disclosure>
  );
}
