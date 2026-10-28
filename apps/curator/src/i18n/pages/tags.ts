/**
 * The tags screen's copy (ADR 0020 §7). The section is merged into `pages` by `i18n/pt.ts` and
 * `i18n/en.ts`; keeping it in its own module is what lets the screen be extracted without touching
 * the central catalogue.
 *
 * `en` is typed as `pt`, so a missing or extra key fails `tsc` — the same gate the central
 * catalogue has. The entries are grouped by the screen's four tabs (`relevance`, `similarity`,
 * `proposals`, `classify`) plus the two pieces they share: `merge` (the panel) and `proposal` (the
 * card).
 */

export const pt = {
  tags: {
    clear: "limpar",
    tabs: {
      relevance: "Relevância",
      similarity: "Similaridade",
      proposals: "Propostas de Mesclagem",
      classify: "Classificar",
    },
    columns: {
      tag: "Tag",
      documents: "Documentos",
      frequency: "Frequência",
      rarity: "Raridade",
      specificity: "Especificidade",
      state: "Estado",
      decide: "Decidir",
    },
    filters: {
      threshold: "Limiar",
      allStatuses: "Todos os status",
      anyReason: "Qualquer motivo",
      minDocs: "Mín. docs",
      onlyFlagged: "só com avisos",
    },
    relevance: {
      countOption: "{count} de uso",
      count: "Contagem",
      usage: "contagem",
      specificityOption: "Especificidade (pune o genérico)",
      specificityWord: "especificidade",
      perPage: "{count} tags",
      hintLabel: "Explicando os metodos",
      hint: "A {usage} mostra o que pesa no acervo; a {specificity} mostra o que caracteriza uma descrição, punindo o que aparece em toda parte. São duas perguntas diferentes: uma acha o que domina, a outra o que distingue.",
    },
    similarity: {
      mergeApplied: "Mesclagem aplicada",
      filterPlaceholder: "Filtrar por nome…",
      intro:
        "Lista termos parecidos que podem ser variações do mesmo assunto. Selecione qual termo deve ser mantido como padrão ao mesclar. É possível selecionar múltiplas linhas para mesclar de uma vez só pela barra inferior. Caso precise reverter alguma mesclagem, consulte a aba Propostas.",
      banCount: "{count} grafia(s) banida(s) no eixo {scope}",
      notExcludes: "não exclui nada",
      banNotice:
        "{banned}. Banir {nothing}: as tags continuam no acervo e alcançáveis pela busca, e a marcação segue de pé porque a mesclagem continua possível. O passo que exclui está em {place}, depois da prévia.",
      mergeMarkedTitle: "Mesclar {count} tags marcadas",
      mergeMarkedHint:
        "Estas tags vieram de linhas diferentes da lista: escolha a canônica abaixo; o impacto é recalculado para o conjunto inteiro.",
      noPairsTitle: "Nenhum par acima do limiar",
      noPairsHint:
        "Baixe o limiar para ver pares mais distantes, ou use Propor Agrupamentos para registrar os conjuntos.",
      pairCountTerm: "{count} par(es) para “{term}” de {total}",
      pairCountAll: "{count} par(es) de {total}",
      clearMarks: "limpar marcação ({count})",
      markRowTitle: "Marcar as duas tags desta linha para mesclar em conjunto",
      markPairAria: "Marcar {first} e {second}",
      mergeArrow: "Mesclar ↦",
      mergeTwoTitle: "Mesclar duas tags",
      markedBar: "{tags} tags marcadas em {rows} linha(s)",
      banScopeAria: "Eixo do banimento",
      banTitle:
        "Banir uma grafia não exclui nada: a tag continua no acervo. A exclusão das tags fica em {place}.",
      banMarked: "Banir {count} marcadas",
    },
    merge: {
      outcome:
        "{label} · {documents} documento(s) atualizado(s) · {tags} tag(s) absorvida(s) · registro {ids}. O desfazer está na aba Propostas.",
      defaultTitle: "Mesclar tags",
      returnToGroup: "Trazer de volta para o agrupamento",
      removeFromGroup: "Tirar do agrupamento",
      includeInGroup: "Incluir {name} no agrupamento",
      keepSpelling: "Manter esta grafia",
      outOfGroup: " — fora do agrupamento",
      keptCanonical: " — mantida (canônica)",
      absorbed: " — absorvida",
      explain:
        "A similaridade não diz qual das duas é a boa: a lista vem crua. Desmarque o que não pertence ao conjunto — “289 anos” não é “294 anos” — e o impacto é recalculado sobre o que sobra.",
      checkingImpact: "Conferindo o impacto…",
      nothingWritten: "Nada foi escrito ainda. A mesclagem trabalha sobre estes mesmos números.",
      counts:
        "{documents} documento(s) atualizado(s) · {links} vínculo(s) reescrito(s) · {tags} tag(s) absorvida(s)",
      impactLine: "{name} {id} ({documents} doc{category})",
      categorySuffix: ", categoria {category}",
      synonymsCreated: "grafias registradas: {list}",
      synonymsRepointed: "grafias redirecionadas: {list}",
      lostCategory:
        "Esta mesclagem {excludes}: a tag absorvida está na categoria {drawers} e a canônica não tem categoria.",
      lostCategoryStrong: "exclui uma classificação de assunto",
      undoNotice:
        "Diferente da mesclagem de entidades, esta {hasUndo}: a aba Propostas guarda a tag, os vínculos, a classificação e as grafias, e restaura tudo.",
      hasUndo: "tem desfazer",
      atLeastTwo: "Um agrupamento precisa de ao menos duas tags: uma canônica e uma absorvida.",
      checkImpactFirst: "Confira o impacto antes de mesclar.",
      mergeOneIn: "Mesclar {name} em {canonical}",
      mergeManyIn: "Mesclar {count} tags em {canonical}",
      done: "{documents} documento(s) atualizado(s) · {tags} tag(s) absorvida(s). Registro {ids}: o desfazer fica na aba Propostas.",
    },
    proposals: {
      suggesting: "Propondo…",
      suggest: "Propor Agrupamentos",
      suggestNotice:
        "Proposta: {found} agrupamento(s) encontrados, {persisted} registrados, {pending} pendentes, {flagged} com aviso. Uma decisão já tomada não é sobrescrita.",
      approvedNotice:
        "{count} agrupamento(s) aprovado(s) nesta página {notMerged}: aprovar registra a intenção, e só aplicar absorve as tags. Enquanto isso não acontece, a lista abaixo não muda.",
      notMerged: "ainda não foram mesclados",
      includeApproved: "incluir as aprovadas desta página",
      searching: "Buscando…",
      selectAllApproved: "selecionar todas as aprovadas",
      fulfilledNotice:
        "{count} agrupamento(s) aprovado(s) nesta página {nothing}: os membros foram mesclados em outra mesclagem (ou excluídos por uma purga). Não são falhas — não há nada a mesclar.",
      nothingToAbsorb: "já não têm o que absorver",
      archiveFulfilled: "arquivar as já cumpridas",
      archiveNote: "Arquivada: os membros já não existem no acervo.",
      editedNote:
        "Editada à mão: a máquina propôs {count} membros e a seleção revisada foi mesclada.",
      selectedCount: "{count} agrupamento(s) selecionado(s) para aplicar",
      batchLimitTitle: "O lote aceita no máximo {max} agrupamentos.",
      applyBatch: "Aplicar em lote",
      batchTooMany: "{count} selecionados: o lote aceita no máximo {max}. Aplique em partes.",
      clearSelection: "limpar seleção",
      batchApplied: "{count} agrupamento(s) aplicado(s)",
      batchSkipped: ", {count} já aplicado(s) antes (ignorados)",
      batchFailed: ", {count} falha(s).",
      appliedLine: "#{id}: {documents} documento(s), {tags} tag(s) absorvida(s) · registro {ids}",
      skippedLine: "#{id} ignorado: {error}",
      failedLine: "#{id} não aplicado: {error}",
      emptyTitle: "Nenhuma proposta com este filtro",
      emptyHint:
        "Use Propor Agrupamentos para registrar os pares acima do limiar. A proposta não mescla nada: ela só registra a pergunta.",
      editedClosed: "Agrupamento #{id} editado e fechado como rejeitado",
      editMergeTitle: "Editar e mesclar o agrupamento #{id}",
      editMergeHint:
        "Desmarque a tag que não pertence ao conjunto e escolha a canônica. Mesclar absorve a seleção revisada, registra o resultado — e fecha esta proposta como rejeitada, porque a pergunta da máquina foi respondida de outro jeito.",
    },
    ledger: {
      title: "Registro das Mesclagens",
      hint: "Registro de mesclagens {concluded}. O histórico mantém os dados e vínculos originais de cada termo, permitindo restaurá-los a qualquer momento pelo botão Desfazer.",
      concluded: "concluídas",
      searchPlaceholder: "Buscar por grafia absorvida ou canônica…",
      reading: "Lendo o registro…",
      emptyNone: "Nenhuma mesclagem feita ainda",
      emptyTerm: "Nenhuma mesclagem para “{term}”",
      emptyHintTerm: "A busca cobre as duas grafias de cada linha: a absorvida e a canônica.",
      emptyHintNone: "O registro guarda cada tag absorvida, com o estado anterior.",
      entryMeta: " · {documents} doc(s) · {date}{by}",
      entryBy: " · por {name}",
      undoneAt: "desfeito em {date}",
      undoTitle: "Restaura a tag, os vínculos, a classificação e as grafias absorvidas.",
      undo: "desfazer",
      seeMore: "ver mais",
      showingFiltered: "mostrando {shown} de {total} mesclagem(ns) que a busca encontrou",
      showingAll: "mostrando {shown} de {total} mesclagem(ns) feitas",
    },
    proposal: {
      documents: "{count} documento(s)",
      includeInBatch: "incluir no lote de aplicação",
      noMembers: "sem membros para absorver",
      membersGoneTitle: "Os membros já não existem no acervo.",
      approve: "Aprovar",
      reject: "Rejeitar",
      edit: "editar",
      editClosing: "fechando edição",
      editTitle: "Tirar membros do agrupamento antes de mesclar",
      decidedBy: "por {name}",
      decisionNote: " · {note}",
      impactLine: "{name} ({documents} doc{category})",
      lostCategory:
        "Esta mesclagem {excludes}: um dos membros está numa categoria que a canônica não tem.",
    },
    classify: {
      allCategories: "Todas as categorias",
      retiredSuffix: " (aposentada)",
      notice:
        "A decisão tomada aqui afeta {everywhere}: ela atualiza a classificação em todos os documentos que contêm o termo. Ao marcar como {notSubject}, a palavra é incluída na lista de grafias bloqueadas para evitar novas ocorrências (os registros existentes continuam intactos até a exclusão, em {place}).",
      everywhere: "todo o sistema",
      notSubject: "não é assunto",
      notSubjectStrong: "Não assunto",
      readingCatalog: "Lendo o catálogo…",
      emptyTitle: "Nenhuma tag neste estado",
      emptyHintPending:
        "A fila está vazia: toda tag do acervo tem categoria ou foi declarada não-assunto.",
      emptyHintOther: "Troque o estado ou limpe a busca para ver outras tags do catálogo.",
      countInState: "{count} tag(s) neste estado",
      reading: "lendo…",
      forTerm: " para “{term}”",
      selectPage: "selecionar esta página",
      clearSelectionCount: "limpar seleção ({count})",
      markedCount: "{count} tag(s) marcada(s)",
      moveToCategory: "Mover para categoria…",
      notSubjectTitle:
        "Nenhum selo de assunto será mostrado para elas, e a grafia não volta a virar tag.",
      reportCategory:
        "“{name}” está em {category}. A decisão vale para todas as descrições que carregam a tag.",
      reportNotSubject:
        "“{name}” foi declarada não-assunto: nenhum selo de assunto será mostrado para ela, o classificador não vai adivinhar de novo e a grafia não volta a virar tag.",
      destinationCategory: "categoria {name}",
      destinationNotSubject: "não-assunto (a grafia não volta a virar tag)",
      bulkReport: "{count} tag(s) com decisão registrada: {destination}.",
      bulkFailed:
        " {count} não responderam (ids {ids}): a decisão delas continua em aberto, e elas seguem marcadas.",
      searchPlaceholder: "Buscar tag…",
    },
    row: {
      markAria: "Marcar {name}",
      confidenceTitle:
        "O que o classificador pontuou antes de recusar a categoria. Ele não errou sozinho: abaixo do limiar, a decisão é sua.",
      confidence: "confiança {score}",
      excludedTitle:
        "Uma pessoa declarou que esta tag não é assunto, e a grafia está banida de voltar.",
      noDecision: "sem decisão",
      noDecisionTitle: "Nenhuma pessoa decidiu, e o classificador não arquivou a tag.",
      categoryAria: "Categoria da tag {name}",
      categoryTitle: "Vale para todas as descrições que carregam a tag, não só para uma.",
      noCategory: "Sem categoria (não é assunto)",
    },
  },
};

export const en: typeof pt = {
  tags: {
    clear: "clear",
    tabs: {
      relevance: "Relevance",
      similarity: "Similarity",
      proposals: "Merge Proposals",
      classify: "Classify",
    },
    columns: {
      tag: "Tag",
      documents: "Documents",
      frequency: "Frequency",
      rarity: "Rarity",
      specificity: "Specificity",
      state: "State",
      decide: "Decide",
    },
    filters: {
      threshold: "Threshold",
      allStatuses: "All statuses",
      anyReason: "Any reason",
      minDocs: "Min. docs",
      onlyFlagged: "flagged only",
    },
    relevance: {
      countOption: "Usage {count}",
      count: "count",
      usage: "count",
      specificityOption: "Specificity (penalises the generic)",
      specificityWord: "specificity",
      perPage: "{count} tags",
      hintLabel: "Explaining the methods",
      hint: "The {usage} shows what weighs on the collection; the {specificity} shows what characterises a description, penalising what appears everywhere. They are two different questions: one finds what dominates, the other what distinguishes.",
    },
    similarity: {
      mergeApplied: "Merge applied",
      filterPlaceholder: "Filter by name…",
      intro:
        "Lists similar terms that may be variations of the same subject. Select which term should be kept as the default when merging. You can select multiple rows to merge at once from the bar below. If you need to revert a merge, check the Proposals tab.",
      banCount: "{count} spelling(s) banned on the {scope} axis",
      notExcludes: "does not exclude anything",
      banNotice:
        "{banned}. Banning {nothing}: the tags stay in the collection and reachable by search, and the selection remains because the merge is still possible. The step that excludes is in {place}, after the preview.",
      mergeMarkedTitle: "Merge {count} marked tags",
      mergeMarkedHint:
        "These tags came from different rows of the list: choose the canonical one below; the impact is recalculated for the whole set.",
      noPairsTitle: "No pair above the threshold",
      noPairsHint:
        "Lower the threshold to see more distant pairs, or use Propose Groupings to record the sets.",
      pairCountTerm: "{count} pair(s) for “{term}” of {total}",
      pairCountAll: "{count} pair(s) of {total}",
      clearMarks: "clear marking ({count})",
      markRowTitle: "Mark both tags of this row to merge them together",
      markPairAria: "Mark {first} and {second}",
      mergeArrow: "Merge ↦",
      mergeTwoTitle: "Merge two tags",
      markedBar: "{tags} tags marked across {rows} row(s)",
      banScopeAria: "Ban axis",
      banTitle:
        "Banning a spelling excludes nothing: the tag stays in the collection. Tag exclusion is in {place}.",
      banMarked: "Ban {count} marked",
    },
    merge: {
      outcome:
        "{label} · {documents} document(s) updated · {tags} tag(s) absorbed · record {ids}. Reverting is in the Proposals tab.",
      defaultTitle: "Merge tags",
      returnToGroup: "Bring back to the grouping",
      removeFromGroup: "Remove from the grouping",
      includeInGroup: "Include {name} in the grouping",
      keepSpelling: "Keep this spelling",
      outOfGroup: " — out of the grouping",
      keptCanonical: " — kept (canonical)",
      absorbed: " — absorbed",
      explain:
        "Similarity does not say which of the two is the good one: the list comes raw. Uncheck what does not belong to the set — “289 anos” is not “294 anos” — and the impact is recalculated over what remains.",
      checkingImpact: "Checking the impact…",
      nothingWritten: "Nothing has been written yet. The merge works on these same numbers.",
      counts:
        "{documents} document(s) updated · {links} link(s) rewritten · {tags} tag(s) absorbed",
      impactLine: "{name} {id} ({documents} doc{category})",
      categorySuffix: ", category {category}",
      synonymsCreated: "registered spellings: {list}",
      synonymsRepointed: "redirected spellings: {list}",
      lostCategory:
        "This merge {excludes}: the absorbed tag is in category {drawers} and the canonical one has no category.",
      lostCategoryStrong: "excludes a subject classification",
      undoNotice:
        "Unlike the entity merge, this one {hasUndo}: the Proposals tab keeps the tag, the links, the classification and the spellings, and restores everything.",
      hasUndo: "can be reverted",
      atLeastTwo: "A grouping needs at least two tags: one canonical and one absorbed.",
      checkImpactFirst: "Check the impact before merging.",
      mergeOneIn: "Merge {name} into {canonical}",
      mergeManyIn: "Merge {count} tags into {canonical}",
      done: "{documents} document(s) updated · {tags} tag(s) absorbed. Record {ids}: reverting is in the Proposals tab.",
    },
    proposals: {
      suggesting: "Proposing…",
      suggest: "Propose Groupings",
      suggestNotice:
        "Proposal: {found} grouping(s) found, {persisted} recorded, {pending} pending, {flagged} with a warning. A decision already made is not overwritten.",
      approvedNotice:
        "{count} approved grouping(s) on this page {notMerged}: approving records the intent, and only the merge absorbs the tags. Until that happens, the list below does not change.",
      notMerged: "have not been merged yet",
      includeApproved: "include this page's approved ones",
      searching: "Searching…",
      selectAllApproved: "select all approved",
      fulfilledNotice:
        "{count} approved grouping(s) on this page {nothing}: the members were merged in another merge (or excluded by a purge). They are not failures — there is nothing to merge.",
      nothingToAbsorb: "no longer have anything to absorb",
      archiveFulfilled: "file away the fulfilled ones",
      archiveNote: "Filed away: the members no longer exist in the collection.",
      editedNote:
        "Edited by hand: the machine proposed {count} members and the revised selection was merged.",
      selectedCount: "{count} grouping(s) selected to merge",
      batchLimitTitle: "The batch accepts at most {max} groupings.",
      applyBatch: "Merge batch",
      batchTooMany: "{count} selected: the batch accepts at most {max}. Do it in parts.",
      clearSelection: "clear selection",
      batchApplied: "{count} grouping(s) merged",
      batchSkipped: ", {count} already merged before (ignored)",
      batchFailed: ", {count} failure(s).",
      appliedLine: "#{id}: {documents} document(s), {tags} tag(s) absorbed · record {ids}",
      skippedLine: "#{id} ignored: {error}",
      failedLine: "#{id} not merged: {error}",
      emptyTitle: "No proposal with this filter",
      emptyHint:
        "Use Propose Groupings to record the pairs above the threshold. The proposal merges nothing: it only records the question.",
      editedClosed: "Grouping #{id} edited and closed as rejected",
      editMergeTitle: "Edit and merge grouping #{id}",
      editMergeHint:
        "Uncheck the tag that does not belong to the set and choose the canonical one. Merging absorbs the revised selection, records the result — and closes this proposal as rejected, because the machine's question was answered another way.",
    },
    ledger: {
      title: "Merge Log",
      hint: "Log of {concluded} merges. The history keeps each term's original data and links, allowing them to be restored at any time with the Revert button.",
      concluded: "completed",
      searchPlaceholder: "Search by absorbed or canonical spelling…",
      reading: "Reading the log…",
      emptyNone: "No merge made yet",
      emptyTerm: "No merge for “{term}”",
      emptyHintTerm:
        "The search covers both spellings of each row: the absorbed one and the canonical one.",
      emptyHintNone: "The log keeps every absorbed tag, with its previous state.",
      entryMeta: " · {documents} doc(s) · {date}{by}",
      entryBy: " · by {name}",
      undoneAt: "reverted on {date}",
      undoTitle: "Restores the tag, the links, the classification and the absorbed spellings.",
      undo: "revert",
      seeMore: "see more",
      showingFiltered: "showing {shown} of {total} merge(s) the search found",
      showingAll: "showing {shown} of {total} merge(s) made",
    },
    proposal: {
      documents: "{count} document(s)",
      includeInBatch: "include in the merge batch",
      noMembers: "no members to absorb",
      membersGoneTitle: "The members no longer exist in the collection.",
      approve: "Approve",
      reject: "Reject",
      edit: "edit",
      editClosing: "closing edit",
      editTitle: "Remove members from the grouping before merging",
      decidedBy: "by {name}",
      decisionNote: " · {note}",
      impactLine: "{name} ({documents} doc{category})",
      lostCategory:
        "This merge {excludes}: one of the members is in a category the canonical one does not have.",
    },
    classify: {
      allCategories: "All categories",
      retiredSuffix: " (retired)",
      notice:
        "The decision taken here affects {everywhere}: it updates the classification in every document that contains the term. Marking it as {notSubject}, the word is added to the blocked spellings list to avoid new occurrences (existing records stay intact until the exclusion, in {place}).",
      everywhere: "the whole system",
      notSubject: "not a subject",
      notSubjectStrong: "Not a subject",
      readingCatalog: "Reading the catalogue…",
      emptyTitle: "No tag in this state",
      emptyHintPending:
        "The queue is empty: every tag in the collection has a category or was declared not a subject.",
      emptyHintOther: "Change the state or clear the search to see other tags in the catalogue.",
      countInState: "{count} tag(s) in this state",
      reading: "reading…",
      forTerm: " for “{term}”",
      selectPage: "select this page",
      clearSelectionCount: "clear selection ({count})",
      markedCount: "{count} tag(s) marked",
      moveToCategory: "Move to category…",
      notSubjectTitle:
        "No subject seal will be shown for them, and the spelling will not become a tag again.",
      reportCategory:
        "“{name}” is in {category}. The decision applies to every description that carries the tag.",
      reportNotSubject:
        "“{name}” was declared not a subject: no subject seal will be shown for it, the classifier will not guess again and the spelling will not become a tag again.",
      destinationCategory: "category {name}",
      destinationNotSubject: "not a subject (the spelling will not become a tag again)",
      bulkReport: "{count} tag(s) with the decision recorded: {destination}.",
      bulkFailed:
        " {count} did not answer (ids {ids}): their decision remains open, and they stay marked.",
      searchPlaceholder: "Search tag…",
    },
    row: {
      markAria: "Mark {name}",
      confidenceTitle:
        "What the classifier scored before refusing the category. It did not err alone: below the threshold, the decision is yours.",
      confidence: "confidence {score}",
      excludedTitle:
        "A person declared this tag is not a subject, and the spelling is banned from coming back.",
      noDecision: "no decision",
      noDecisionTitle: "No person decided, and the classifier did not file the tag.",
      categoryAria: "Category of tag {name}",
      categoryTitle: "Applies to every description that carries the tag, not just one.",
      noCategory: "No category (not a subject)",
    },
  },
};
