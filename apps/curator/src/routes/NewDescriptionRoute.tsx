import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";

import {
  createManualIngestion,
  fetchCurrentUser,
  previewAccessPoints,
  searchTags,
  type AccessPointPreviewItem,
  type ManualIngestionRequest,
} from "@/api/client";
import { queries } from "@/api/queries";
import { AccessPointsField, type AccessPointChip } from "@/components/description/AccessPointsField";
import { IsadFieldControl } from "@/components/description/IsadFieldControl";
import { CsvImportPanel } from "@/components/ingestion/CsvImportPanel";
import { PageBody } from "@/components/layout/PageBody";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { Input, Select } from "@/components/ui/Input";
import { Notice } from "@/components/ui/Notice";
import { Tabs } from "@/components/ui/Tabs";
import { DIGITAL_OBJECT } from "@/lib/copy";
import { descricoes, formatCount, formatDate } from "@/lib/format";
import { fieldsOfArea, ISAD_AREAS, type IsadAreaId } from "@/lib/isad";
import { routeMessage } from "@/lib/messages";
import { can } from "@/lib/permissions";
import { asEnum } from "@/lib/search";
import { groupAccessPointPreview } from "@/lib/taxonomy";

const routeApi = getRouteApi("/acervo/nova");

/** The two input shapes of the same job: the typed record and the CSV. */
export type NewDescriptionMode = "digitar" | "csv";

export type NewDescriptionSearch = { modo?: NewDescriptionMode };

export function validateNewDescriptionSearch(search: Record<string, unknown>): NewDescriptionSearch {
  return { modo: asEnum(search.modo, ["digitar", "csv"] as const) };
}

const MODES: { id: NewDescriptionMode; label: string }[] = [
  { id: "digitar", label: "Digitar" },
  { id: "csv", label: "Importar CSV" },
];

/**
 * The type-ahead of the access points: the catalogue tags that match, with the weight and the
 * drawer the dossier already shows. The floor of two characters belongs to the API.
 */
async function searchTagOptions(term: string) {
  const results = await searchTags(term);
  return results.map((result) => ({
    tagId: result.tag_id,
    name: result.name,
    hint: `${descricoes(result.document_count)}${
      result.macro_category_name ? ` · ${result.macro_category_name}` : " · sem categoria"
    }`,
  }));
}

/** One request for the settled string; the server reads it with the transfer's classifier. */
async function previewAccessPointOptions(indexingPoints: string): Promise<AccessPointPreviewItem[]> {
  const response = await previewAccessPoints({ indexing_points: indexingPoints });
  return response.items;
}

const ACCESS_POINTS_COPY = {
  placeholder: "Busque uma tag ou digite um termo novo",
  add: (term: string) => `Adicionar “${term}”`,
  remove: (name: string) => `Remover ${name}`,
  searching: "Buscando…",
  searchFailed: "Não foi possível buscar no catálogo. Pressione Enter para usar o termo digitado.",
  duplicate: (term: string) => `“${term}” já está na lista.`,
  previewFailed: "Não foi possível conferir os pontos de acesso; eles serão enviados como digitados.",
};

/**
 * The one sentence the field says about the whole string.
 *
 * The summary is "news only": an existing tag in its canonical spelling produces no line. It says
 * what the transfer will discard and why, what it will create, and what it will map to a synonym,
 * so the archivist can remove a term before saving instead of discovering the loss in the dossier.
 * The chips themselves are never rewritten or removed here; the decision stays with the person.
 */
function describeAccessPoints(items: AccessPointPreviewItem[]): ReactNode {
  const groups = groupAccessPointPreview(items);
  const lines: ReactNode[] = [];

  // The warning first: a term that will be discarded is the one that asks for an action.
  for (const item of groups.dropped) {
    const reason =
      item.status === "STOPWORD"
        ? "é um termo bloqueado"
        : item.status === "TOO_SHORT"
          ? "é curto demais (mínimo de 3 caracteres)"
          : "é longo demais (máximo de 100 caracteres)";
    const label = item.status === "TOO_LONG" ? `“${item.input.slice(0, 30)}…”` : `“${item.input}”`;
    lines.push(
      <li key={`dropped-${item.status}-${item.input}`} className="text-(--color-warn)">
        {label} {reason} e será descartado.
      </li>,
    );
  }

  if (groups.created.length > 0) {
    const labels = groups.created.map((item) => {
      const name = item.name ?? item.input;
      return name === item.input ? `“${name}”` : `“${item.input}” → “${name}”`;
    });
    lines.push(
      <li key="created" className="text-(--color-muted)">
        {groups.created.length === 1
          ? `${labels[0]} será criado no arquivamento.`
          : `Serão criados no arquivamento: ${labels.join(", ")}.`}
      </li>,
    );
  }

  for (const item of groups.synonyms) {
    lines.push(
      <li key={`synonym-${item.input}`} className="text-(--color-muted)">
        “{item.input}” será ligado a “{item.name ?? item.input}”.
      </li>,
    );
  }

  for (const item of groups.respelled) {
    lines.push(
      <li key={`respelled-${item.input}`} className="text-(--color-muted)">
        “{item.input}” já está no catálogo como “{item.name}”.
      </li>,
    );
  }

  if (lines.length === 0) return null;
  return <ul className="grid gap-1">{lines}</ul>;
}

/**
 * The entry paths into the collection: one description typed in full, or a CSV imported.
 *
 * Both are inputs to the same pipeline and neither is an approval: the submit writes `raw_data`, a
 * `DONE` queue row and the staging record (or, for the CSV, the rows), enqueues the same `transfer`
 * the scraper uses and lets the AI see the descriptions; the archive description is born
 * `PENDING_AI`, and the dossier is where it is reviewed.
 *
 * The screen lives in the Acervo because that is the object it creates, not a configuration of the
 * ingestion stage. Its two modes are tabs in the URL — the typed form and the browser-side CSV parse
 * are different input shapes of the same job — so a link can open the import directly with
 * `?modo=csv`. The panes stay mounted while the other one is active: the form is ~thirty controls,
 * and looking at the CSV must not throw a draft away.
 *
 * The fields come from `lib/isad.ts`, the same catalogue the dossier edits, so the two screens
 * cannot grow two vocabularies for one norm.
 */
export function NewDescriptionRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const modo = search.modo ?? "digitar";

  const current = useQuery({ queryKey: ["current-user"], queryFn: fetchCurrentUser, retry: false });
  const role = current.data?.role ?? "VIEWER";
  const canCurate = can(role, "CURATE");

  return (
    <>
      <PageHeader screen="newDescription" />

      {/*
        The two input shapes are tabs, not two doors: they write the same staging and the same queue,
        and the header carries the destination once. The mode lives in the URL so a link can open the
        import directly.
      */}
      <div className="px-6 pt-4">
        <Tabs
          items={MODES}
          active={modo}
          onChange={(id) => {
            const next = MODES.find((item) => item.id === id)?.id;
            navigate({ to: "/acervo/nova", search: { modo: next === "digitar" ? undefined : next } });
          }}
        />
      </div>

      <PageBody className="gap-3">
        {!canCurate ? (
          <Notice tone="warn" as="div">
            Sua conta não pode criar descrições. Peça a um curador ou a um administrador da instalação.
          </Notice>
        ) : null}

        {/*
          Both panes stay mounted while the other is active: the typed form is ~thirty controls, and
          looking at the CSV import must not throw a draft away. `hidden` and not unmounting is what
          preserves it; the inactive pane is display:none, so it takes no focus and no space.
        */}
        <div hidden={modo !== "digitar"} className="grid gap-3">
          <ManualEntryForm canCurate={canCurate} />
        </div>

        <div hidden={modo !== "csv"}>
          <CsvImportPanel />
        </div>
      </PageBody>
    </>
  );
}

/** The typed record: the whole ISAD(G) form, with its own draft and its own result. */
function ManualEntryForm({ canCurate }: { canCurate: boolean }) {
  const queryClient = useQueryClient();

  const levels = useQuery(queries.levels());
  const languages = useQuery(queries.languages());

  const [descriptionId, setDescriptionId] = useState(() => `manual-${crypto.randomUUID()}`);
  const [values, setValues] = useState<Record<string, string>>({});
  const [accessPoints, setAccessPoints] = useState<AccessPointChip[]>([]);
  // The chips control owns the input text; a remount is the one clean way to clear it on reset.
  const [formVersion, setFormVersion] = useState(0);

  const valueOf = (name: string) => values[name] ?? "";
  const setValue = (name: string, value: string) => {
    setValues((previous) => ({ ...previous, [name]: value }));
  };

  const changeAccessPoints = (next: AccessPointChip[]) => {
    setAccessPoints(next);
    setValue("indexing_points", next.map((chip) => chip.name).join(", "));
  };

  const selectedLevel = levels.data?.find((level) => level.name === values.level);
  const needsParent = selectedLevel?.requires_parent === true && !values.parent_reference_code?.trim();

  // The title is the one required field of the manual contract, and this is its single definition:
  // the submit button and the sentence beside it both read it, so the red mark on the field and the
  // greyed-out button cannot disagree about *why* the form cannot be sent.
  const titleMissing = valueOf("title").trim().length === 0;

  const submit = useMutation({
    mutationFn: () => createManualIngestion(toBody(descriptionId, values)),
    onSuccess: () => {
      // The origin's pending count and the ledger both moved: the record is staged and a transfer
      // may have been queued. A new id keeps a second submit from colliding with the first.
      void queryClient.invalidateQueries({ queryKey: ["ingestion", "origins"] });
      void queryClient.invalidateQueries({ queryKey: ["system", "runs"] });
      setDescriptionId(`manual-${crypto.randomUUID()}`);
    },
  });

  const reset = () => {
    submit.reset();
    setValues({});
    setAccessPoints([]);
    setFormVersion((version) => version + 1);
    setDescriptionId(`manual-${crypto.randomUUID()}`);
  };

  // The form asks only what the catalogue marks as a creation field: the description control area
  // is the dossier's (a record being born has no wording rules to declare yet).
  const fieldsForForm = (area: IsadAreaId) => fieldsOfArea(area).filter((field) => field.manualEntry !== false);

  const identityFields = fieldsForForm("identity");

  return (
    <>
      {submit.data ? (
        <Notice tone="ok" as="div" className="grid gap-2">
          <p className="font-medium">{routeMessage(submit.data)}</p>
          <p className="font-mono text-xs">{submit.data.data.description_id}</p>
          {submit.data.data.document_date ? (
            <p className="text-xs">
              Data registrada: <strong>{formatDate(submit.data.data.document_date)}</strong>
              {submit.data.data.date_expression
                ? ` — como está na fonte: “${submit.data.data.date_expression}”.`
                : "."}
            </p>
          ) : null}
          <p className="text-xs">
            O registro aparece no acervo quando a transferência rodar. Até lá, o dossiê ainda pode
            responder “não encontrado”.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to="/acervo/$descriptionId"
              params={{ descriptionId: submit.data.data.description_id }}
              className="text-sm underline"
            >
              Abrir o dossiê
            </Link>
            <Button size="sm" variant="secondary" onClick={reset}>
              Criar outra em branco
            </Button>
          </div>
        </Notice>
      ) : null}
      {submit.error ? <ErrorState error={submit.error} /> : null}

      <form
        className="grid gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          submit.mutate();
        }}
      >
        <Disclosure
          header={
            <span className="flex flex-wrap items-baseline gap-2">
              <span className="text-sm font-semibold">3.1 Identidade</span>
            </span>
          }
          defaultOpen
          toggleLabel="Abrir a área"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            {/*
              The asterisk is `aria-hidden` on purpose: the label already names the input, and the
              mandatory-ness travels through `required` on the control, which every screen reader
              announces — an asterisk read aloud would say "asterisk" and nothing more. Red is never
              the only signal: the star, the attribute and the sentence beside the disabled button
              say the same thing three ways.
            */}
            <Field
              label={
                <>
                  Título <span aria-hidden="true" className="text-(--color-danger)">*</span>
                </>
              }
              hint="Campo obrigatório."
            >
              <Input
                required
                value={valueOf("title")}
                maxLength={500}
                autoFocus
                onChange={(event) => setValue("title", event.target.value)}
              />
            </Field>
            <Field label="Nível de Descrição">
              <Select value={valueOf("level")} onChange={(event) => setValue("level", event.target.value)}>
                <option value="">— não classificado —</option>
                {levels.data?.map((level) => (
                  <option key={level.level_id} value={level.name}>
                    {level.name} ({formatCount(level.document_count)})
                  </option>
                ))}
              </Select>
            </Field>

            <Field
              label="Unidade Pai / Superior"
              hint="Selecione o código da unidade à qual esta pertence."
            >
              <Input
                value={valueOf("parent_reference_code")}
                maxLength={500}
                placeholder="BR PRADAP SMU"
                onChange={(event) => setValue("parent_reference_code", event.target.value)}
              />
            </Field>

            {needsParent ? (
              <p className="text-xs text-(--color-warn) sm:col-span-2">
                O nível “{selectedLevel?.name}” pede uma unidade superior. Você pode gravar assim mesmo:
                o registro entra pendente e o vínculo se faz na aba Arranjo do dossiê.
              </p>
            ) : null}

            {identityFields.map((field) => (
              <IsadFieldControl
                key={field.name}
                field={field}
                value={valueOf(field.name)}
                languages={languages.data ?? []}
                onChange={(value) => setValue(field.name, value)}
                hint={field.help}
                dateAs="expression"
              />
            ))}
          </div>
        </Disclosure>

        {ISAD_AREAS.filter((area) => area.id !== "identity").map((area) => {
          const fields = fieldsForForm(area.id);
          const filled = fields.filter((field) => valueOf(field.name).trim() !== "").length;
          return (
            <Disclosure
              key={area.id}
              header={
                <span className="flex flex-wrap items-baseline gap-2">
                  <span className="text-sm font-semibold">{area.title}</span>
                  <span className="text-xs text-(--color-muted)">{area.hint}</span>
                  {filled > 0 ? (
                    <span className="rounded bg-black/[0.05] px-1.5 text-xs">{filled} preenchido(s)</span>
                  ) : null}
                </span>
              }
              toggleLabel="Abrir a área"
            >
              <div className="grid gap-3 sm:grid-cols-2">
                {fields.map((field) => (
                  <IsadFieldControl
                    key={field.name}
                    field={field}
                    value={valueOf(field.name)}
                    languages={languages.data ?? []}
                    onChange={(value) => setValue(field.name, value)}
                    hint={field.help}
                    dateAs="expression"
                  />
                ))}
                {area.id === "context" ? (
                  <Field
                    label="URL da Fonte"
                    hint="Página de onde o registro veio, quando houver."
                  >
                    <Input
                      value={valueOf("original_url")}
                      placeholder="https://…"
                      onChange={(event) => setValue("original_url", event.target.value)}
                    />
                  </Field>
                ) : null}
              </div>
            </Disclosure>
          );
        })}

        <Disclosure
          header={
            <span className="flex flex-wrap items-baseline gap-2">
              <span className="text-sm font-semibold">Pontos de Acesso</span>
              <span className="text-xs text-(--color-muted)">Os assuntos que viraram tags no acervo.</span>
            </span>
          }
          toggleLabel="Abrir a área"
        >
          {/*
            Access points are chips over the catalogue: the type-ahead brings what already exists,
            the explicit "add" keeps the archivist's spelling, and the summary below the control
            says what the transfer will create, map or discard. The wire is still
            `indexing_points: str | None` — the same string the CSV column and the scraper's mapped
            key carry — so this screen does not change the contract (#229).
          */}
          <Field
            label="Pontos de Acesso"
            hint="Escolha tags do catálogo ou digite termos novos. Termos novos viram tags quando a descrição for arquivada."
            htmlFor="manual-access-points"
            hintId="manual-access-points-hint"
          >
            <AccessPointsField
              key={formVersion}
              id="manual-access-points"
              chips={accessPoints}
              onChange={changeAccessPoints}
              search={searchTagOptions}
              preview={previewAccessPointOptions}
              describe={describeAccessPoints}
              copy={ACCESS_POINTS_COPY}
              describedBy="manual-access-points-hint"
            />
          </Field>
        </Disclosure>

        {/*
          The upload control is disabled on purpose, with the sentence defined once in `copy.ts` and
          shared with the dossier: #198 owns the digital object. The image URL below it is the one
          path that works today — the thumbnail worker copies that image into the storage.
        */}
        <Card>
          <CardHeader className="text-sm font-semibold">{DIGITAL_OBJECT.label}</CardHeader>
          <CardBody className="grid gap-3 sm:grid-cols-2">
            <div className="grid content-start gap-2">
              <input
                type="file"
                disabled
                aria-label={DIGITAL_OBJECT.label}
                title={DIGITAL_OBJECT.disabled}
                className="text-sm text-(--color-muted)"
              />
              <p className="text-xs text-(--color-muted)">{DIGITAL_OBJECT.hint}</p>
            </div>
            <Field
              label="URL da Imagem"
              hint="Se a imagem já está publicada em outro lugar, a cópia para o acervo é feita automaticamente."
            >
              <Input
                value={valueOf("thumb_down_link")}
                placeholder="https://…"
                onChange={(event) => setValue("thumb_down_link", event.target.value)}
              />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardBody className="flex flex-wrap items-center gap-3">
            <Button
              type="submit"
              variant="primary"
              disabled={submit.isPending || titleMissing || !canCurate}
            >
              {submit.isPending ? "Salvando…" : "Salvar"}
            </Button>
            {/* The reason the button is greyed out, where the archivist is looking when it happens:
                the asterisk on the field is at the top of a form of ~30 controls. */}
            {titleMissing && canCurate ? (
              <span className="text-xs text-(--color-danger)">Falta preencher o título.</span>
            ) : null}
            <span className="text-xs text-(--color-muted)">
              id do formulário: <span className="font-mono">{descriptionId}</span>
            </span>
          </CardBody>
        </Card>
      </form>
    </>
  );
}

/**
 * The request body, derived from the contract's own model.
 *
 * Every field is listed so a rename in `ManualIngestionRequest` breaks the compile instead of being
 * silently dropped by the API — the failure mode the request-model gate exists to prevent on the
 * server side.
 */
function toBody(descriptionId: string, values: Record<string, string>): ManualIngestionRequest {
  const text = (name: string): string | null => {
    const value = values[name]?.trim();
    return value ? value : null;
  };

  return {
    description_id: descriptionId,
    title: text("title") ?? "",
    document_date: text("document_date"),
    reference_code: text("reference_code"),
    level: text("level"),
    parent_reference_code: text("parent_reference_code"),
    dimension_support: text("dimension_support"),
    producers: text("producers"),
    admin_bio_history: text("admin_bio_history"),
    admin_archival_history: text("admin_archival_history"),
    provenance: text("provenance"),
    scope_content: text("scope_content"),
    appraisal_destruction: text("appraisal_destruction"),
    accruals: text("accruals"),
    arrangement: text("arrangement"),
    access_conditions: text("access_conditions"),
    reproduction_conditions: text("reproduction_conditions"),
    language_name: text("language_name"),
    physical_characteristics: text("physical_characteristics"),
    finding_aids: text("finding_aids"),
    originals_location: text("originals_location"),
    copies_location: text("copies_location"),
    related_units: text("related_units"),
    publication_notes: text("publication_notes"),
    conservation_notes: text("conservation_notes"),
    general_notes: text("general_notes"),
    archivist_notes: text("archivist_notes"),
    rules_conventions: text("rules_conventions"),
    indexing_points: text("indexing_points"),
    original_url: text("original_url"),
    thumb_down_link: text("thumb_down_link"),
  };
}
