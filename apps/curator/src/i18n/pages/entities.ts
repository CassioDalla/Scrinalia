/**
 * The entities screen's copy (ADR 0020 §7). The section is merged into `pages` by `i18n/pt.ts` and
 * `i18n/en.ts`; keeping it in its own module is what lets the screen be extracted without touching
 * the central catalogue.
 *
 * The section is `entitiesScreen`, not `entities`: the top-level `entities` section already owns the
 * type, origin, merge-flag, exclusion-source and conflict-winner vocabularies, and spreading over it
 * would overwrite them.
 *
 * `pt` is deliberately not `as const`: `en` is typed as its shape, and a literal type would demand
 * the Portuguese text in the English catalogue. Without it the keys are still fixed — a missing or
 * extra key is a `tsc` failure — which is the parity ADR 0020 §1 asks for.
 */

export const pt = {
  entitiesScreen: {
    status: "{names} nomes por relevância · {links} vínculos entre os listados",
    purgeOrphans: "Excluir órfãs",
    purgeTitle: "Excluir as entidades que nenhuma descrição carrega — não há como desfazer.",
    purgedCount: "{count} excluídas.",
    notice:
      "{reclassify} Ao corrigir o tipo, o extrator passa a reconhecer aquela grafia com o tipo novo em toda extração futura. E {merge}: o painel mostra o impacto antes do clique, e cada entidade absorvida fica registrada antes de a mesclagem acontecer.",
    noticeReclassify: "Reclassificar não é renomear um rótulo.",
    noticeMerge: "mesclar tem desfazer",
    tabRelevance: "Relevância",
    tabSimilarity: "Similaridade",
    tabDescriptions: "Descrições",
    allTypes: "Todos os tipos",
    markedHint: "Marcadas: {count} · marque ao menos duas para mesclar",
    markHint: "Marque duas ou mais para mesclar; o tipo se corrige na própria linha.",
    emptyTitle: "Nenhuma entidade neste tipo",
    emptyHint: "A extração de nomes ainda não rodou neste acervo, ou o tipo escolhido não tem nomes.",
    openDescriptions: "Ver as descrições de {name}",
    usageBadgeTitle: "Descrições que carregam este nome",
    selectEntity: "Selecionar {name}",
    typeField: "Tipo",
    renameTitle: "Corrigir a grafia deste nome, sem mesclar com outra entidade",
    renameAria: "Renomear {name}",
    deleteOrphanTitle: "Nenhuma descrição carrega este nome: excluir não perde vínculo, e não há como desfazer.",
    nameField: "Nome",
    unsaved: "alterações não salvas",
    keepOldSpelling:
      "Manter a grafia antiga como sinônimo — é o que faz a grafia antiga continuar levando a esta entidade nas próximas extrações. Desmarque quando a grafia antiga for um erro de digitação.",
    renameKept:
      "A grafia antiga continua levando a esta entidade. O desfazer está no histórico, no fim desta tela.",
    renameNotKept: "A grafia antiga não foi mantida. O desfazer está no histórico, no fim desta tela.",
    noDescriptionsTitle: "Nenhuma descrição carrega este nome",
    noDescriptionsHint:
      "O nome existe no vocabulário e nenhuma descrição o carrega — é a linha que a exclusão de órfãs remove.",
    mergeByNameTrigger: "+ Mesclar pelo nome",
    mergeByNameToggle: "Mesclar duas entidades escritas pelo nome",
    mergeByNameTitle: "Mesclar pelo nome",
    mergeByNameHint:
      "Mesclagem manual de termos que não apareceram nas sugestões automáticas. Digite as duas grafias para mesclá-las em um único termo. Itens selecionados na aba Relevância não são transferidos para cá.",
    mergeSearchPlaceholder: "digite ao menos 2 letras: smu…",
    mergeSearchEmpty: "nenhuma entidade com esse trecho",
    noMembersHint: "Nenhum nome escolhido ainda. Escreva as duas grafias que você já sabe que são uma só.",
    needTwoHint: "Uma mesclagem precisa de duas grafias — com menos do que isso, nada é mesclado.",
    mergeChosenTitle: "Mesclar os nomes escolhidos",
    mergeChosenHint:
      "A canônica é escolha sua. O desfazer de cada entidade absorvida fica no histórico, no fim desta tela.",
    mergeCount: "Mesclar {count} entidades",
    canonicalSuffix: " — mantida (canônica)",
    absorbedSuffix: " — absorvida",
    renameCanonicalField: "Renomear a Canônica (opcional; o nome antigo vira sinônimo)",
    previewPending: "Calculando o impacto…",
    previewSummary:
      "{descriptions} descrição(ões) passam a carregar {canonical} · {links} vínculo(s) movido(s) · {entities} entidade(s) absorvida(s).",
    absorbNotice:
      "As {count} entidades absorvidas deixam de existir e seus vínculos passam para {name}. As grafias viram sinônimos, e o extrator continua reconhecendo-as. A mesclagem é registrada {before} de acontecer — o desfazer restaura a linha, os vínculos e as grafias.",
    /** The emphasised word `absorbNotice` carries in `{before}`. */
    beforeMerge: "antes",
    mergeOne: "Mesclar {absorbed} em {canonical}",
    mergeMany: "Mesclar {count} nomes em {canonical}",
    undoTitle: "Restaura cada entidade absorvida, seus vínculos e as grafias.",
    undoMerge: "Desfazer esta mesclagem",
    undoAlsoInLedger: "O desfazer também está no histórico abaixo.",
    mergeResult:
      "{links} vínculo(s) movido(s) · {entities} entidade(s) absorvida(s) · registros {ids} no histórico.",
    ledgerTitle: "Histórico dos nomes: mesclagens e renomeações",
    ledgerHint:
      "Aqui só entram decisões já concluídas. Cada linha guarda o {state} — na mesclagem, a entidade, seus vínculos, suas grafias e o nome que a canônica perdeu; na renomeação, o nome antigo e se ele ficou como sinônimo — e o desfazer restaura tudo.",
    ledgerState: "estado anterior",
    ledgerSearchPlaceholder: "buscar por grafia absorvida ou canônica…",
    ledgerReading: "Lendo o histórico…",
    ledgerEmptyTerm: "Nenhum registro para “{term}”",
    ledgerEmpty: "Nenhuma decisão sobre nomes ainda",
    ledgerEmptyTermHint:
      "A busca cobre as duas grafias de cada linha: a absorvida (ou a antiga) e a canônica.",
    ledgerEmptyHint:
      "O histórico registra cada entidade absorvida numa mesclagem e cada nome renomeado, com o estado anterior.",
    ledgerRename: "· renomeação · {date}",
    ledgerBy: "· por {name}",
    ledgerDocs: "· {count} doc(s) · {date}",
    ledgerCanonicalWas: "· canônica era “{name}”",
    ledgerUndone: "desfeito em {date}",
    undoRenameTitle: "Devolve o nome anterior e desfaz o sinônimo que a renomeação criou.",
    undoMergeTitle: "Restaura a entidade, seus vínculos, suas grafias e o nome da canônica.",
    seeMore: "Ver mais",
    ledgerCount: "{shown} de {total}",
    similarityTargetField: "Nome-Alvo (vazio: todos os pares parecidos)",
    similarityTargetPlaceholder: "ex.: prefeitura",
    similarityThresholdField: "Limiar de similaridade",
    similarityHint:
      "O par é evidência, não decisão: nomes parecidos na grafia também podem ser nomes diferentes. A canônica é escolha sua, e mesclar aqui é a mesma operação da aba Relevância — o histórico guarda cada absorvida e o desfazer restaura. Para mesclar mais de um par de uma vez, marque as linhas e use a barra que aparece embaixo.",
    similarityEmptyTitle: "Nenhum par acima do limiar",
    similarityEmptyHint:
      "Com esse limiar e nenhum par, o vocabulário pode já estar limpo — ou o alvo não existe.",
    mergeMarkedTitle: "Mesclar {count} entidades marcadas",
    mergeMarkedHint:
      "Estas entidades vieram de linhas diferentes da lista: a canônica é escolhida abaixo. O histórico guarda cada absorvida e o desfazer restaura.",
    showAllPairs: "Mostrar todos os {count} pares",
    neighbourHint: "vizinho de “{target}” — para mesclar, deixe o nome-alvo vazio e use a lista de pares",
    markRowTitle: "Marcar as duas entidades desta linha para mesclar em conjunto",
    markRowAria: "Marcar {first} e {second}",
    mergeArrow: "Mesclar ↦",
    chooseCanonicalTitle: "Escolher a canônica e mesclar",
    identicalNamesHint:
      "Os dois nomes são idênticos nesta linha: confira os identificadores antes de decidir.",
    markedStatus: "{count} entidades marcadas em {rows} linha(s)",
    mergeEntities: "Mesclar entidades",
    clearMarked: "Limpar",
    seeAlso: "Veja também os {conflicts} e a tela {exclusions}.",
    /** What the `{conflicts}` link in `seeAlso` says; the exclusions link uses its screen label. */
    conflictsLink: "conflitos com o eixo de assunto",
  },
};

export const en: typeof pt = {
  entitiesScreen: {
    status: "{names} names by relevance · {links} links among those listed",
    purgeOrphans: "Delete orphans",
    purgeTitle: "Delete the entities no description carries — there is no undo.",
    purgedCount: "{count} deleted.",
    notice:
      "{reclassify} Correcting the type makes the extractor recognise that spelling with the new type in every future extraction. And {merge}: the panel shows the impact before the click, and every absorbed entity is recorded before the merge happens.",
    noticeReclassify: "Reclassifying is not renaming a label.",
    noticeMerge: "merging has an undo",
    tabRelevance: "Relevance",
    tabSimilarity: "Similarity",
    tabDescriptions: "Descriptions",
    allTypes: "All types",
    markedHint: "Marked: {count} · mark at least two to merge",
    markHint: "Mark two or more to merge; the type is corrected on the row itself.",
    emptyTitle: "No entity of this type",
    emptyHint: "Name extraction has not run on this collection yet, or the chosen type has no names.",
    openDescriptions: "See the descriptions of {name}",
    usageBadgeTitle: "Descriptions that carry this name",
    selectEntity: "Select {name}",
    typeField: "Type",
    renameTitle: "Correct the spelling of this name without merging it into another entity",
    renameAria: "Rename {name}",
    deleteOrphanTitle: "No description carries this name: deleting loses no link, and there is no undo.",
    nameField: "Name",
    unsaved: "unsaved changes",
    keepOldSpelling:
      "Keep the old spelling as a synonym — that is what makes the old spelling keep leading to this entity in future extractions. Uncheck it when the old spelling was a typo.",
    renameKept: "The old spelling still leads to this entity. The undo is in the history at the bottom of this screen.",
    renameNotKept:
      "The old spelling was not kept. The undo is in the history at the bottom of this screen.",
    noDescriptionsTitle: "No description carries this name",
    noDescriptionsHint:
      "The name exists in the vocabulary and no description carries it — it is the row the orphan purge removes.",
    mergeByNameTrigger: "+ Merge by name",
    mergeByNameToggle: "Merge two entities written by name",
    mergeByNameTitle: "Merge by name",
    mergeByNameHint:
      "Manual merge of terms that did not appear in the automatic suggestions. Type the two spellings to merge them into a single term. Items selected on the Relevance tab are not transferred here.",
    mergeSearchPlaceholder: "type at least 2 letters: smu…",
    mergeSearchEmpty: "no entity with that fragment",
    noMembersHint: "No name chosen yet. Write the two spellings you already know are one.",
    needTwoHint: "A merge needs two spellings — with fewer than that, nothing is merged.",
    mergeChosenTitle: "Merge the chosen names",
    mergeChosenHint:
      "The canonical one is your choice. The undo of each absorbed entity is in the history at the bottom of this screen.",
    mergeCount: "Merge {count} entities",
    canonicalSuffix: " — kept (canonical)",
    absorbedSuffix: " — absorbed",
    renameCanonicalField: "Rename the Canonical (optional; the old name becomes a synonym)",
    previewPending: "Calculating the impact…",
    previewSummary:
      "{descriptions} description(s) will carry {canonical} · {links} link(s) moved · {entities} entity(ies) absorbed.",
    absorbNotice:
      "The {count} absorbed entities cease to exist and their links move to {name}. The spellings become synonyms, and the extractor keeps recognising them. The merge is recorded {before} it happens — the undo restores the row, the links and the spellings.",
    beforeMerge: "before",
    mergeOne: "Merge {absorbed} into {canonical}",
    mergeMany: "Merge {count} names into {canonical}",
    undoTitle: "Restores each absorbed entity, its links and the spellings.",
    undoMerge: "Undo this merge",
    undoAlsoInLedger: "The undo is also in the history below.",
    mergeResult: "{links} link(s) moved · {entities} entity(ies) absorbed · records {ids} in the history.",
    ledgerTitle: "Name history: merges and renames",
    ledgerHint:
      "Only completed decisions enter here. Each row keeps the {state} — on a merge, the entity, its links, its spellings and the name the canonical lost; on a rename, the old name and whether it stayed as a synonym — and the undo restores everything.",
    ledgerState: "previous state",
    ledgerSearchPlaceholder: "search by absorbed or canonical spelling…",
    ledgerReading: "Reading the history…",
    ledgerEmptyTerm: "No record for “{term}”",
    ledgerEmpty: "No decision about names yet",
    ledgerEmptyTermHint:
      "The search covers both spellings of each row: the absorbed one (or the old one) and the canonical one.",
    ledgerEmptyHint:
      "The history records each entity absorbed in a merge and each renamed name, with the previous state.",
    ledgerRename: "· rename · {date}",
    ledgerBy: "· by {name}",
    ledgerDocs: "· {count} doc(s) · {date}",
    ledgerCanonicalWas: "· canonical was “{name}”",
    ledgerUndone: "undone on {date}",
    undoRenameTitle: "Returns the previous name and undoes the synonym the rename created.",
    undoMergeTitle: "Restores the entity, its links, its spellings and the canonical's name.",
    seeMore: "See more",
    ledgerCount: "{shown} of {total}",
    similarityTargetField: "Target Name (empty: all similar pairs)",
    similarityTargetPlaceholder: "e.g.: city hall",
    similarityThresholdField: "Similarity threshold",
    similarityHint:
      "The pair is evidence, not a decision: names similar in spelling can also be different names. The canonical one is your choice, and merging here is the same operation as the Relevance tab — the history keeps each absorbed one and the undo restores. To merge more than one pair at once, mark the rows and use the bar that appears below.",
    similarityEmptyTitle: "No pair above the threshold",
    similarityEmptyHint:
      "With this threshold and no pair, the vocabulary may already be clean — or the target does not exist.",
    mergeMarkedTitle: "Merge {count} marked entities",
    mergeMarkedHint:
      "These entities came from different rows of the list: the canonical one is chosen below. The history keeps each absorbed one and the undo restores.",
    showAllPairs: "Show all {count} pairs",
    neighbourHint:
      "neighbour of “{target}” — to merge, leave the target name empty and use the pairs list",
    markRowTitle: "Mark both entities of this row to merge them together",
    markRowAria: "Mark {first} and {second}",
    mergeArrow: "Merge ↦",
    chooseCanonicalTitle: "Choose the canonical and merge",
    identicalNamesHint:
      "The two names are identical on this row: check the identifiers before deciding.",
    markedStatus: "{count} entities marked in {rows} row(s)",
    mergeEntities: "Merge entities",
    clearMarked: "Clear",
    seeAlso: "See also the {conflicts} and the {exclusions} screen.",
    conflictsLink: "conflicts with the subject axis",
  },
};
