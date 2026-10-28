/**
 * Screen copy merged into `pages` by `i18n/pt.ts` and `i18n/en.ts`; keeping it in its own module
 * is what lets the screen be extracted in a git worktree without touching the central catalogue.
 *
 * The arrangement, as the archivist navigates it: the tree screen that shows where each description
 * sits, and the plan screen that decides the rungs the tree is materialised from.
 */

export const pt = {
  tree: {
    /** The action in the header; the create panel repeats it on its own button. */
    createNode: "Criar nó",
    /** The warning strip above the tree when the arrangement has not been materialised. */
    orphan: {
      count: "{count} descrições ainda estão sem unidade superior.",
      body: "Abaixo você vê apenas o que já foi organizado; o restante permanece na raiz aguardando definição.",
      link: "Ver o diagnóstico",
    },
    roots: {
      reading: "Lendo as raízes…",
      emptyTitle: "Nenhuma descrição na raiz",
      emptyHint:
        "O acervo está vazio ou todas as descrições já foram devidamente organizadas sob uma unidade superior.",
      showing: "Mostrando {shown} de {total} raízes.",
    },
    /** What the right-hand pane says before the archivist picks a node. */
    chooseNode: {
      title: "Escolha um nó à esquerda",
      hint: "A árvore exibe a estrutura hierárquica do acervo: cada item em seu devido lugar. Se você prefere buscar por assunto ou termos específicos, utilize a {list}.",
      list: "lista",
    },
    /** Declaring a node the collection never delivered. */
    create: {
      title: "Criar nova Unidade de Descrição",
      hint: "Utilize esta opção quando precisar inserir uma unidade (Fundo, Seção ou Série) que não veio nos dados originais. O novo item será criado como aprovado manualmente.",
      parentLabel: "Onde o nó entra",
      atRoot: "na raiz",
      underSelected: "sob o nó selecionado",
      underSelectedNode: "sob o nó selecionado: {label}",
      underSelectedNone: "sob o nó selecionado (escolha um nó na árvore)",
      referenceCode: "Código de Referência",
      referenceCodePlaceholder: "ex.: BR PRADAP SMU ED",
      titleField: "Título",
      choose: "— escolher —",
      scope: "Âmbito e conteúdo (opcional)",
      required: "Código, título e nível são obrigatórios.",
    },
    node: {
      expand: "Expandir",
      collapse: "Recolher",
      orphanBadge: "sem pai",
    },
    /** The children read lazily, when a node is opened. */
    branch: {
      readError: "não foi possível ler este ramo",
      noChildren: "sem filhos",
    },
    /** The selected node: its ancestors, its children and the descriptions inside it. */
    panel: {
      noParent: "sem unidade superior",
      childOne: "filho direto",
      childMany: "filhos diretos",
      open: "abrir a descrição",
      title: "Descrições neste ramo",
      searchPlaceholder: "buscar dentro do ramo…",
      emptyTitle: "Nenhuma descrição neste ramo",
      emptyTerm: "O termo não aparece em nenhuma descrição deste ramo. A busca não sai do ramo de propósito.",
      emptyNoTerm: "Este nó não tem descrições próprias; os filhos é que as carregam.",
      showing: "Mostrando 25 de {total}. Refine a busca ou use a {list}.",
      list: "lista facetada",
    },
  },
  plan: {
    status: "{matching} de {total} degraus",
    statusWithFilter: "{matching} de {total} degraus · {status}",
    createNodeTitle: "Declarar um nó que a importação não trouxe",
    createNode: "Criar nó na árvore ↗",
    suggesting: "Propondo…",
    suggest: "Propor níveis",
    intro:
      "A máquina lê os códigos de referência e propõe os degraus; a decisão é sua. Nada é criado no acervo até a materialização — e uma decisão tomada nunca é sobrescrita por uma nova proposta. O sinal à esquerda recolhe o ramo; o cartão abre no clique para decidir o degrau.",
    suggestion:
      "Proposta: {created} degrau(s) novo(s), {refreshed} atualizado(s), {preserved} decisão(ões) preservada(s). Total no catálogo: {total}.",
    filters: {
      allFlags: "Todos os avisos",
      codePlaceholder: "Filtrar por código…",
      branches: "Ramos:",
      expandAll: "Expandir tudo",
      collapseAll: "Recolher tudo",
      collapseDecided: "Recolher os decididos",
      collapseDecidedTitle: "Fecha os ramos que não têm nenhum degrau aguardando decisão.",
      notice: "O filtro mostra os degraus que casam, os pais e os ramos deles.",
    },
    empty: {
      noneTitle: "Nenhum degrau proposto",
      noneHint:
        "A proposta lê os códigos de referência do acervo e lista o que há para decidir — nada é criado no acervo.",
      filteredTitle: "Nenhum degrau com este filtro",
      filteredHint: "Há degraus no catálogo, mas nenhum corresponde ao aviso ou ao código digitado.",
      clearFilters: "Limpar filtros",
    },
    /** The branch toggle of one list level, and the indentation cap stated on hover. */
    branch: {
      expand: "Expandir os degraus abaixo",
      collapse: "Recolher os degraus abaixo",
      depthTitle: "profundidade {depth} (recuada no limite)",
    },
    /** What a collapsed branch says about the rungs it hides. */
    hidden: {
      one: "1 degrau oculto",
      many: "{count} degraus ocultos",
      pendingOne: "1 aguardando decisão",
      pendingMany: "{count} aguardando decisão",
      sentence: "{rungs} · {waiting}",
    },
    card: {
      toggleDecide: "Decidir este degrau",
      toggleView: "Ver a decisão e as amostras",
      materialised: "materializado",
      awaiting: "aguardando decisão",
      depth: "profundidade {depth}",
      parent: "· pai: {parent}",
      root: "raiz",
      documents: "· {count} descrição(ões)",
      declaredLevels: "· níveis declarados: {levels}",
      none: "nenhum",
      level: "nível: {level}",
      title: " · título: {title}",
      decidedBy: " · decidido por {name}",
      decidedAt: " · {date}",
      note: " · nota: {note}",
      collapseInto: "Este degrau {emphasis} {code}: na materialização, o ramo abaixo sobe para ele.",
      reopenTitle: "Devolve o degrau para “sugerido”: a próxima proposta pode atualizar a evidência de novo.",
      reopen: "Reabrir decisão",
      samples: "amostras:",
      levelInferred: "Nível de Descrição (inferido, não declarado)",
      chooseLevel: "Escolha o nível",
      titleField: "Título do Nó",
      mergeField: "Fundir em (este degrau é o mesmo nível que…)",
      mergePlaceholder: "código de outro degrau",
      approveNeedsLevel: "Para aprovar, escolha o nível de descrição: sem ele a aprovação é recusada.",
      reopenHint: "Reabrir devolve o degrau para “sugerido”: a próxima proposta volta a atualizar a evidência.",
    },
  },
};

export const en: typeof pt = {
  tree: {
    createNode: "Create node",
    orphan: {
      count: "{count} descriptions still have no parent unit.",
      body: "Below you see only what has already been organised; the rest stays at the root awaiting a decision.",
      link: "See the diagnostics",
    },
    roots: {
      reading: "Reading the roots…",
      emptyTitle: "No description at the root",
      emptyHint:
        "The collection is empty, or every description has already been properly organised under a parent unit.",
      showing: "Showing {shown} of {total} roots.",
    },
    chooseNode: {
      title: "Choose a node on the left",
      hint: "The tree shows the collection's hierarchical structure: each item in its proper place. If you would rather search by subject or specific terms, use the {list}.",
      list: "list",
    },
    create: {
      title: "Create a new Description Unit",
      hint: "Use this when you need to insert a unit (Fonds, Section or Series) that did not come in the original data. The new item is created as manually approved.",
      parentLabel: "Where the node goes",
      atRoot: "at the root",
      underSelected: "under the selected node",
      underSelectedNode: "under the selected node: {label}",
      underSelectedNone: "under the selected node (choose a node in the tree)",
      referenceCode: "Reference Code",
      referenceCodePlaceholder: "e.g.: BR PRADAP SMU ED",
      titleField: "Title",
      choose: "— choose —",
      scope: "Scope and content (optional)",
      required: "Code, title and level are required.",
    },
    node: {
      expand: "Expand",
      collapse: "Collapse",
      orphanBadge: "no parent",
    },
    branch: {
      readError: "could not read this branch",
      noChildren: "no children",
    },
    panel: {
      noParent: "no parent unit",
      childOne: "direct child",
      childMany: "direct children",
      open: "open the description",
      title: "Descriptions in this branch",
      searchPlaceholder: "search within the branch…",
      emptyTitle: "No description in this branch",
      emptyTerm: "The term does not appear in any description of this branch. The search does not leave the branch, on purpose.",
      emptyNoTerm: "This node has no descriptions of its own; the children carry them.",
      showing: "Showing 25 of {total}. Refine the search or use the {list}.",
      list: "faceted list",
    },
  },
  plan: {
    status: "{matching} of {total} rungs",
    statusWithFilter: "{matching} of {total} rungs · {status}",
    createNodeTitle: "Declare a node the import did not bring",
    createNode: "Create node in the tree ↗",
    suggesting: "Proposing…",
    suggest: "Propose levels",
    intro:
      "The machine reads the reference codes and proposes the rungs; the decision is yours. Nothing is created in the collection until materialisation — and a decision already taken is never overwritten by a new proposal. The sign on the left collapses the branch; the card opens on click to decide the rung.",
    suggestion:
      "Proposal: {created} new rung(s), {refreshed} updated, {preserved} decision(s) preserved. Total in the catalogue: {total}.",
    filters: {
      allFlags: "All flags",
      codePlaceholder: "Filter by code…",
      branches: "Branches:",
      expandAll: "Expand all",
      collapseAll: "Collapse all",
      collapseDecided: "Collapse the decided ones",
      collapseDecidedTitle: "Closes the branches with no rung awaiting a decision.",
      notice: "The filter shows the matching rungs, their parents and their branches.",
    },
    empty: {
      noneTitle: "No rung proposed",
      noneHint:
        "The proposal reads the collection's reference codes and lists what there is to decide — nothing is created in the collection.",
      filteredTitle: "No rung with this filter",
      filteredHint: "There are rungs in the catalogue, but none matches the flag or the typed code.",
      clearFilters: "Clear filters",
    },
    branch: {
      expand: "Expand the rungs below",
      collapse: "Collapse the rungs below",
      depthTitle: "depth {depth} (indented at the limit)",
    },
    hidden: {
      one: "1 hidden rung",
      many: "{count} hidden rungs",
      pendingOne: "1 awaiting a decision",
      pendingMany: "{count} awaiting a decision",
      sentence: "{rungs} · {waiting}",
    },
    card: {
      toggleDecide: "Decide this rung",
      toggleView: "View the decision and the samples",
      materialised: "materialised",
      awaiting: "awaiting a decision",
      depth: "depth {depth}",
      parent: "· parent: {parent}",
      root: "root",
      documents: "· {count} description(s)",
      declaredLevels: "· declared levels: {levels}",
      none: "none",
      level: "level: {level}",
      title: " · title: {title}",
      decidedBy: " · decided by {name}",
      decidedAt: " · {date}",
      note: " · note: {note}",
      collapseInto: "This rung {emphasis} {code}: at materialisation the branch below moves up into it.",
      reopenTitle: "Returns the rung to “suggested”: the next proposal may update the evidence again.",
      reopen: "Reopen decision",
      samples: "samples:",
      levelInferred: "Description Level (inferred, not declared)",
      chooseLevel: "Choose the level",
      titleField: "Node Title",
      mergeField: "Merge into (this rung is the same level as…)",
      mergePlaceholder: "code of another rung",
      approveNeedsLevel: "To approve, choose the description level: without it the approval is refused.",
      reopenHint: "Reopening returns the rung to “suggested”: the next proposal updates the evidence again.",
    },
  },
};
