import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import {
  createHierarchyNode,
  type HierarchyNodeCreateRequest,
  type HierarchyNodeSummary,
} from "@/api/client";
import { queries, TREE_PAGE_SIZE } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton, Spinner } from "@/components/ui/Feedback";
import { Input, Select } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import { formatCount, formatDate, REVIEW_STATUS_LABEL, REVIEW_STATUS_TONE } from "@/lib/format";
import { nodeLabel } from "@/lib/hierarchy";

const routeApi = getRouteApi("/acervo/arvore");

export type TreeSearch = { raiz?: string; termo?: string };

export function validateTreeSearch(search: Record<string, unknown>): TreeSearch {
  return {
    raiz: typeof search.raiz === "string" && search.raiz.length > 0 ? search.raiz : undefined,
    termo: typeof search.termo === "string" && search.termo.length > 0 ? search.termo : undefined,
  };
}

/** How deep a branch is opened in one click. Beyond that the archivist expands again. */
const BRANCH_DEPTH = 1;

/**
 * The arrangement as navigation.
 *
 * **Arranjo is not assunto.** This screen is the objective axis — where a description sits in the
 * provenance — and the subject badges live in the list and the dossier. Mixing them here would
 * teach the archivist to "fix" a subject by dragging a description into another branch.
 *
 * The reads are lazy on purpose. The roots come from ``max_depth=0`` (a handful, not the whole
 * collection) and each expansion is ``root_id=X&max_depth=1``, one indexed prefix of the
 * materialised path. Loading the forest flat would read thousands of rows and still be truncated
 * by the page limit, which is how a tree screen ends up quietly lying about the collection.
 *
 * When the arrangement has not been materialised, the diagnostics say so: the screen shows the
 * ``ORPHAN`` count and points at the plan, instead of drawing a flat list that looks like a
 * broken tree.
 */
export function TreeRoute() {
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);

  const roots = useQuery(queries.tree(undefined, 0));
  const summary = useQuery(queries.diagnosticSummary());

  const orphans = summary.data?.counts?.ORPHAN ?? 0;
  const selected = search.raiz;

  const toggle = (descriptionId: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(descriptionId)) next.delete(descriptionId);
      else next.add(descriptionId);
      return next;
    });

  return (
    <>
      <PageHeader
        title="Árvore arquivística"
        subtitle="Navegação pelo arranjo materializado. Escolher um nó mostra o ramo e as descrições que ele contém."
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant={creating ? "secondary" : "primary"}
              onClick={() => setCreating((current) => !current)}
            >
              {creating ? "cancelar criação" : "Criar nó"}
            </Button>
            <Link to="/arranjo/plano">
              <Button size="sm">Plano de arranjo</Button>
            </Link>
          </div>
        }
      />

      {orphans > 0 ? (
        <div className="border-b border-(--color-warn)/20 bg-(--color-warn)/5 px-6 py-2 text-xs text-(--color-warn)">
          <strong>{formatCount(orphans)} descrições ainda não têm unidade superior.</strong> O que
          aparece abaixo é só o que já foi materializado — o resto continua na raiz, esperando a decisão
          das rungs.{" "}
          <Link to="/arranjo/diagnostico" className="underline">
            Ver o diagnóstico
          </Link>
          .
        </div>
      ) : null}

      <div className="flex min-h-0">
        <aside className="w-96 shrink-0 overflow-y-auto border-r border-(--color-line) bg-(--color-surface)">
          {roots.isPending ? <Spinner label="Lendo as raízes…" /> : null}
          {roots.error ? (
            <div className="p-4">
              <ErrorState error={roots.error} />
            </div>
          ) : null}

          {roots.data && (roots.data.items ?? []).length === 0 ? (
            <div className="p-4">
              <EmptyState
                title="Nenhuma descrição na raiz"
                hint="O acervo está vazio ou todas as descrições já estão sob alguma unidade superior. Este é o estado final esperado depois da materialização."
              />
            </div>
          ) : null}

          <ul className="py-1">
            {(roots.data?.items ?? []).map((node) => (
              <TreeNode
                key={node.description_id}
                node={node}
                depth={0}
                selected={selected}
                expanded={expanded}
                onSelect={(id) => navigate({ to: "/acervo/arvore", search: { ...search, raiz: id } })}
                onToggle={toggle}
              />
            ))}
          </ul>

          {roots.data && (roots.data.total ?? 0) > (roots.data.items ?? []).length ? (
            <p className="px-4 py-2 text-xs text-(--color-muted)">
              Mostrando {formatCount((roots.data.items ?? []).length)} de {formatCount(roots.data.total ?? 0)}{" "}
              raízes.
            </p>
          ) : null}
        </aside>

        <div className="min-w-0 flex-1 px-6 py-5">
          {creating ? (
            <div className="mb-4">
              <CreateNodePanel
                selectedId={selected ?? null}
                onClose={() => setCreating(false)}
                onCreated={(created) => {
                  setCreating(false);
                  // The new child only shows if its parent is open, and selecting it puts the
                  // archivist in front of what was just declared.
                  if (created.parent_id) {
                    setExpanded((current) => new Set(current).add(created.parent_id as string));
                  }
                  void navigate({ to: "/acervo/arvore", search: { ...search, raiz: created.description_id } });
                }}
              />
            </div>
          ) : null}

          {selected ? (
            <BranchPanel
              descriptionId={selected}
              term={search.termo}
              onTerm={(termo) =>
                navigate({ to: "/acervo/arvore", search: { ...search, termo: termo || undefined } })
              }
            />
          ) : (
            <EmptyState
              title="Escolha um nó à esquerda"
              hint={
                <>
                  A árvore é o eixo do arranjo: cada descrição tem um lugar. Se o que você procura é
                  por assunto, use a <Link to="/acervo/lista" className="underline">lista</Link> — lá os
                  assuntos são badges e filtros.
                </>
              }
            />
          )}
        </div>
      </div>
    </>
  );
}

/**
 * Declares an arrangement node the collection never delivered.
 *
 * The plan decides the rungs the slicer proposed out of the reference codes; a Fundo, a Seção or a
 * Série **without documents** has no code to be sliced out of, and this is the only way to declare
 * it. The ladder is validated against the chosen parent by the same code a move uses, so the
 * refusals shown here are the API's — not a second copy of the rules living in the screen.
 *
 * The parent is limited to "the root" or "the node I am looking at" on purpose: the route takes a
 * ``description_id``, and inventing a node type-ahead for it would be a new surface for a case the
 * arrangement already answers — you navigate to the parent and declare the child under it.
 */
function CreateNodePanel({
  selectedId,
  onCreated,
  onClose,
}: {
  selectedId: string | null;
  onCreated: (node: HierarchyNodeSummary) => void;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const levels = useQuery(queries.levels());
  const parent = useQuery({ ...queries.node(selectedId ?? ""), enabled: selectedId !== null });

  const [atRoot, setAtRoot] = useState(selectedId === null);
  const [referenceCode, setReferenceCode] = useState("");
  const [title, setTitle] = useState("");
  const [levelId, setLevelId] = useState<number | null>(null);
  const [scopeContent, setScopeContent] = useState("");

  const create = useMutation({
    mutationFn: () => {
      const body: HierarchyNodeCreateRequest = {
        reference_code: referenceCode.trim(),
        title: title.trim(),
        level_id: levelId,
        parent_id: atRoot ? null : selectedId,
        scope_content: scopeContent.trim() || null,
        changed_by: null,
        note: null,
      };
      return createHierarchyNode(body);
    },
    onSuccess: (node) => {
      void queryClient.invalidateQueries({ queryKey: ["hierarchy", "tree"] });
      void queryClient.invalidateQueries({ queryKey: ["hierarchy", "diagnostics"] });
      void queryClient.invalidateQueries({ queryKey: ["hierarchy", "node"] });
      void queryClient.invalidateQueries({ queryKey: ["curation", "inbox"] });
      onCreated(node);
    },
  });

  const valid =
    referenceCode.trim().length > 0 && title.trim().length > 0 && levelId !== null;

  return (
    <Card className="ring-(--color-accent)/40">
      <CardHeader className="text-sm font-semibold">Criar um nó que a origem não entregou</CardHeader>
      <CardBody className="grid gap-3">
        <p className="text-xs text-(--color-muted)">
          Um Fundo, uma Seção ou uma Série <strong>sem documentos</strong> não sai de nenhum código de
          referência, e o plano só decide as rungs que o fatiador propôs. Declarar aqui é o outro
          caminho: a descrição nasce <code>HUMAN_APPROVED</code> e a escada é validada contra o pai
          escolhido pela mesma regra do mover.
        </p>

        <div className="grid gap-2 text-xs">
          <span className="text-(--color-muted)">Onde o nó entra</span>
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2">
              <input type="radio" name="create-node-parent" checked={atRoot} onChange={() => setAtRoot(true)} />
              <span>na raiz</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="create-node-parent"
                checked={!atRoot}
                disabled={selectedId === null}
                onChange={() => setAtRoot(false)}
              />
              <span className={selectedId === null ? "text-(--color-muted)" : undefined}>
                sob o nó selecionado
                {parent.data?.node ? `: ${nodeLabel(parent.data.node)}` : selectedId === null ? " (escolha um nó na árvore)" : ""}
              </span>
            </label>
          </div>
        </div>

        <div className="grid gap-2 sm:grid-cols-3">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Código de referência</span>
            <Input
              value={referenceCode}
              onChange={(event) => setReferenceCode(event.target.value)}
              placeholder="ex.: BR PRADAP SMU ED"
              maxLength={500}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Título</span>
            <Input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={300} />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Nível de descrição</span>
            <Select
              value={levelId ?? ""}
              onChange={(event) => setLevelId(event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">— escolher —</option>
              {(levels.data ?? []).map((level) => (
                <option key={level.level_id} value={level.level_id}>
                  {level.ordinal}. {level.name}
                </option>
              ))}
            </Select>
          </label>
        </div>

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Escopo e conteúdo (opcional)</span>
          <Input value={scopeContent} onChange={(event) => setScopeContent(event.target.value)} />
        </label>

        {levels.error ? <ErrorState error={levels.error} /> : null}
        {parent.error ? <ErrorState error={parent.error} /> : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" disabled={!valid || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "Criando…" : "Criar nó"}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            cancelar
          </Button>
          {!valid ? (
            <span className="text-xs text-(--color-muted)">
              Código, título e nível são obrigatórios — o nível é a decisão que o código não sabe tomar.
            </span>
          ) : null}
        </div>

        {create.error ? <ErrorState error={create.error} /> : null}
      </CardBody>
    </Card>
  );
}

/**
 * One node of the tree, expandable in place.
 *
 * The expansion is a read of its own: ``root_id=node``, one level. Nothing is fetched until the
 * archivist asks, so opening the screen costs one query for the roots and not one for the
 * collection.
 */
function TreeNode({
  node,
  depth,
  selected,
  expanded,
  onSelect,
  onToggle,
}: {
  node: HierarchyNodeSummary;
  depth: number;
  selected?: string;
  expanded: Set<string>;
  onSelect: (descriptionId: string) => void;
  onToggle: (descriptionId: string) => void;
}) {
  const isOpen = expanded.has(node.description_id);
  const isSelected = selected === node.description_id;
  const hasChildren = (node.children_count ?? 0) > 0;

  return (
    <li>
      <div
        className={cn(
          "flex items-center gap-1 border-b border-(--color-line)/60 pr-3 text-sm",
          isSelected ? "bg-(--color-accent)/10" : "hover:bg-black/[0.03]",
        )}
        style={{ paddingLeft: `${depth * 14 + 4}px` }}
      >
        <button
          aria-label={isOpen ? "Recolher" : "Expandir"}
          aria-expanded={isOpen}
          disabled={!hasChildren}
          onClick={() => onToggle(node.description_id)}
          className={cn(
            "grid size-5 shrink-0 place-items-center rounded text-[10px]",
            hasChildren ? "text-(--color-muted) hover:bg-black/5" : "text-transparent",
          )}
        >
          {isOpen ? "▾" : "▸"}
        </button>

        <button
          onClick={() => onSelect(node.description_id)}
          className="flex min-w-0 flex-1 items-center gap-2 py-1 text-left"
        >
          <span className={cn("truncate", isSelected && "font-medium text-(--color-accent)")} title={node.title ?? undefined}>
            {nodeLabel(node)}
          </span>
          {node.level ? <span className="shrink-0 text-[10px] text-(--color-muted)">{node.level}</span> : null}
          {hasChildren ? (
            <span className="shrink-0 text-[10px] text-(--color-muted) tabular-nums">
              {formatCount(node.children_count ?? 0)}
            </span>
          ) : null}
          {node.is_orphan ? <Badge tone="warn">sem pai</Badge> : null}
        </button>
      </div>

      {isOpen ? <Branch nodeId={node.description_id} depth={depth} selected={selected} expanded={expanded} onSelect={onSelect} onToggle={onToggle} /> : null}
    </li>
  );
}

/** The children of one node, read when the node is opened and not before. */
function Branch({
  nodeId,
  depth,
  selected,
  expanded,
  onSelect,
  onToggle,
}: {
  nodeId: string;
  depth: number;
  selected?: string;
  expanded: Set<string>;
  onSelect: (descriptionId: string) => void;
  onToggle: (descriptionId: string) => void;
}) {
  const branch = useQuery(queries.tree(nodeId, BRANCH_DEPTH));
  const children = (branch.data?.items ?? []).filter((child) => child.description_id !== nodeId);

  if (branch.isPending) {
    return (
      <div style={{ paddingLeft: `${(depth + 1) * 14 + 8}px` }} className="py-1">
        <Skeleton className="h-4 w-40" />
      </div>
    );
  }
  if (branch.error) {
    return (
      <div style={{ paddingLeft: `${(depth + 1) * 14 + 8}px` }} className="py-1 text-xs text-(--color-danger)">
        não foi possível ler este ramo
      </div>
    );
  }
  if (children.length === 0) {
    return (
      <p
        style={{ paddingLeft: `${(depth + 1) * 14 + 8}px` }}
        className="py-1 text-xs text-(--color-muted)"
      >
        sem filhos
      </p>
    );
  }

  return (
    <ul>
      {children.map((child) => (
        <TreeNode
          key={child.description_id}
          node={child}
          depth={depth + 1}
          selected={selected}
          expanded={expanded}
          onSelect={onSelect}
          onToggle={onToggle}
        />
      ))}
    </ul>
  );
}

/**
 * The selected node: its branch, its children and the descriptions inside it.
 *
 * "Inside it" uses the existing ``ancestor_id`` facet, so the search is the same code path as the
 * list — a second implementation would be a second definition of "documents of this branch".
 */
function BranchPanel({
  descriptionId,
  term,
  onTerm,
}: {
  descriptionId: string;
  term?: string;
  onTerm: (term: string) => void;
}) {
  const node = useQuery(queries.node(descriptionId));
  const documents = useQuery(
    queries.documents({ ancestor_id: descriptionId, term, limit: 25 }),
  );

  if (node.isPending) return <Spinner label="Lendo a descrição…" />;
  if (node.error) return <ErrorState error={node.error} />;

  const detail = node.data;
  const summary = detail?.node;
  const ancestors = detail?.ancestors ?? [];
  const children = detail?.children ?? [];

  return (
    <div className="grid gap-4">
      <div>
        <nav className="flex flex-wrap items-center gap-1 text-xs text-(--color-muted)">
          {ancestors.map((ancestor) => (
            <span key={ancestor.description_id} className="flex items-center gap-1">
              <Link
                to="/acervo/arvore"
                search={{ raiz: ancestor.description_id }}
                className="hover:underline"
                title={ancestor.title ?? undefined}
              >
                {nodeLabel(ancestor)}
              </Link>
              <span>›</span>
            </span>
          ))}
          <span className="text-(--color-ink)">
            {summary ? nodeLabel(summary) : descriptionId}
          </span>
        </nav>

        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold" title={summary?.title ?? undefined}>
            {summary ? nodeLabel(summary) : descriptionId}
          </h2>
          {summary?.level ? <Badge tone="neutral">{summary.level}</Badge> : null}
          {summary?.is_orphan ? <Badge tone="warn">sem unidade superior</Badge> : null}
          <code className="text-xs text-(--color-muted)">{summary?.reference_code ?? "—"}</code>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-(--color-muted)">
          <span>
            {formatCount(children.length)} {children.length === 1 ? "filho direto" : "filhos diretos"}
          </span>
          <span>·</span>
          <Link
            to="/acervo/$descriptionId"
            params={{ descriptionId }}
            search={{ aba: "arranjo" }}
            className="underline"
          >
            abrir a descrição
          </Link>
        </div>
      </div>

      {children.length > 0 ? (
        <Card>
          <CardBody className="flex flex-wrap gap-2">
            {children.map((child) => (
              <Link
                key={child.description_id}
                to="/acervo/arvore"
                search={{ raiz: child.description_id }}
                title={child.title ?? undefined}
                className="rounded-full bg-black/5 px-2 py-1 text-xs hover:bg-black/10"
              >
                {nodeLabel(child)}
                {child.children_count ? (
                  <span className="ml-1 text-(--color-muted)">({child.children_count})</span>
                ) : null}
              </Link>
            ))}
          </CardBody>
        </Card>
      ) : null}

      <section className="grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Descrições neste ramo</h3>
          <div className="w-72">
            <Input
              value={term ?? ""}
              onChange={(event) => onTerm(event.target.value)}
              placeholder="buscar dentro do ramo…"
            />
          </div>
        </div>

        {documents.error ? <ErrorState error={documents.error} /> : null}
        {documents.isPending ? <Spinner /> : null}
        {documents.data && documents.data.total === 0 ? (
          <EmptyState
            title="Nenhuma descrição neste ramo"
            hint={
              term
                ? "O termo não aparece em nenhuma descrição deste ramo. A busca não sai do ramo de propósito."
                : "Este nó não tem descrições próprias; os filhos é que as carregam."
            }
          />
        ) : null}

        <ul className="space-y-2">
          {documents.data?.items.map((document) => (
            <li key={document.description_id}>
              <Card className="transition hover:ring-(--color-accent)/40">
                <CardBody className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link
                      to="/acervo/$descriptionId"
                      params={{ descriptionId: document.description_id }}
                      className="truncate text-sm font-medium hover:underline"
                    >
                      {document.final_title || document.original_title}
                    </Link>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-(--color-muted)">
                      <span>{formatDate(document.document_date)}</span>
                      {document.level ? <span>· {document.level}</span> : null}
                      {document.reference_code ? (
                        <code className="rounded bg-black/[0.05] px-1">{document.reference_code}</code>
                      ) : null}
                    </div>
                  </div>
                  <Badge tone={REVIEW_STATUS_TONE[document.review_status]}>
                    {REVIEW_STATUS_LABEL[document.review_status]}
                  </Badge>
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>

        {documents.data && documents.data.total > TREE_PAGE_SIZE ? (
          <p className="text-xs text-(--color-muted)">
            Mostrando 25 de {formatCount(documents.data.total)}. Refine a busca ou use a{" "}
            <Link to="/acervo/lista" search={{ ancestor_id: descriptionId }} className="underline">
              lista facetada
            </Link>
            .
          </p>
        ) : null}
      </section>
    </div>
  );
}
