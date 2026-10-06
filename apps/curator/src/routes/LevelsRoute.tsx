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
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Input } from "@/components/ui/Input";
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
        title="Catálogo de níveis"
        subtitle={
          levels.data
            ? `${rows.length} níveis · ${formatCount(withDocuments)} descrições classificadas`
            : "Lendo a escada…"
        }
      />

      <div className="grid max-w-5xl gap-4 px-6 py-5">
        <p className="rounded-md bg-(--color-accent)/5 px-3 py-2 text-xs text-(--color-accent) ring-1 ring-(--color-accent)/20">
          A norma é o padrão, não a lei — mas ela é a assimetria que sustenta a carga: um nível
          desconhecido que chega da origem <strong>entra</strong> (a descrição fica sem nível e o
          diagnóstico a lista), enquanto o arquivista <strong>não</strong> pode gravar um nível que
          não existe. Sem isso, uma lote inteiro falharia por causa de uma grafia nova.
        </p>

        {levels.error ? <ErrorState error={levels.error} /> : null}
        {levels.isPending ? (
          <div className="grid gap-2">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-20" />
            ))}
          </div>
        ) : null}

        <section className="grid gap-2">
          {rows.map((level) => (
            <LevelCard key={level.level_id} level={level} onChanged={invalidate} />
          ))}
        </section>

        <CreateLevelCard onCreated={invalidate} />
      </div>
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
    <Card>
      <CardBody className="grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Badge tone="accent" title="Posição na escada; não é editável depois de criada">
              {level.ordinal}
            </Badge>
            <span className="text-sm font-medium">{level.name}</span>
            <code className="text-xs text-(--color-muted)">{level.code}</code>
            {level.is_active ? <Badge tone="ok">ativo</Badge> : <Badge tone="neutral">desativado</Badge>}
            <Badge tone="neutral" title="Descrições classificadas neste nível">
              {descricoes(level.document_count ?? 0)}
            </Badge>
          </div>
          <Button
            size="sm"
            variant={level.is_active ? "ghost" : "secondary"}
            disabled={save.isPending}
            onClick={() => save.mutate({ is_active: !level.is_active })}
          >
            {level.is_active ? "desativar" : "reativar"}
          </Button>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Nome</span>
            <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={60} />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Grafias aceitas (separadas por vírgula)</span>
            <Input
              value={aliases}
              onChange={(event) => setAliases(event.target.value)}
              placeholder="ex.: subsérie, sub-serie"
            />
          </label>
        </div>

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Descrição (o que o arquivista lê)</span>
          <Input value={description} onChange={(event) => setDescription(event.target.value)} />
        </label>

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
            {save.isPending ? "Salvando…" : "Salvar"}
          </Button>
          {dirty ? <span className="text-xs text-(--color-muted)">alterações não salvas</span> : null}
        </div>
        {save.error ? <ErrorState error={save.error} /> : null}
      </CardBody>
    </Card>
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
    <Card>
      <CardHeader className="text-sm font-semibold">Acrescentar um degrau</CardHeader>
      <CardBody className="grid gap-2">
        <p className="text-xs text-(--color-muted)">
          O ordinal é a posição na escada: um nível só pode ser filho de outro de ordinal menor. Ele
          não é editável depois — mudá-lo renumeraria a árvore, e a árvore passada foi decidida contra
          estes números. Um ordinal novo e um código novo são uma rung nova.
        </p>
        <div className="grid gap-2 sm:grid-cols-4">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Ordinal</span>
            <Input
              type="number"
              min={0}
              value={draft.ordinal}
              onChange={(event) => setDraft({ ...draft, ordinal: Number(event.target.value) })}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Código</span>
            <Input
              value={draft.code}
              onChange={(event) => setDraft({ ...draft, code: event.target.value })}
              placeholder="ex.: serie"
              maxLength={20}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Nome</span>
            <Input
              value={draft.name}
              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              placeholder="ex.: Série"
              maxLength={60}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Grafias aceitas</span>
            <Input value={aliases} onChange={(event) => setAliases(event.target.value)} />
          </label>
        </div>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Descrição</span>
          <Input
            value={draft.description ?? ""}
            onChange={(event) => setDraft({ ...draft, description: event.target.value || null })}
          />
        </label>
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
            {create.isPending ? "Cadastrando…" : "Cadastrar nível"}
          </Button>
        </div>
        {create.error ? <ErrorState error={create.error} /> : null}
      </CardBody>
    </Card>
  );
}
