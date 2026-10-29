/**
 * The collection list and the typology catalogue's copy (ADR 0020 §7). The section is merged into
 * `pages` by `i18n/pt.ts` and `i18n/en.ts`; keeping it in its own module is what lets the screens be
 * extracted without touching the central catalogue.
 *
 * `en` is typed as `pt`, so a missing or extra key fails `tsc` — the same gate the central catalogue
 * has. `collection` holds the list and its filters; `typologies` holds the catalogue and the
 * classifier's refusal queue.
 */

export const pt = {
  collection: {
    /** The select's three rankings, in the order the URL validator accepts them. */
    mode: {
      lexical: "Palavra-chave",
      semantic: "Por Significado",
      hybrid: "Busca Combinada",
    },
    /** The heading each notice gives the ranking it describes. */
    modeTitle: {
      lexical: "Busca por Palavra-chave",
      semantic: "Busca por Significado",
      hybrid: "Busca Combinada",
    },
    notice: {
      lexical:
        "{title}: Localiza exatamente as palavras digitadas. Ideal para quando você já sabe o título, código ou termo específico.",
      semantic:
        "A {title} encontra documentos pelo contexto, mesmo que não tenham a palavra exata. Se você souber o termo exato, a busca por palavra-chave costuma ser mais rápida.",
      hybrid:
        "A {title} une o melhor dos dois mundos: encontra termos exatos e entende o significado do texto. É a opção mais recomendada para encontrar o que você precisa sem se preocupar.",
    },
    searchPlaceholder: "Buscar no acervo…",
    clearSearch: "Limpar busca",
    clearFilters: "Limpar filtros",
    removeFilter: "Clique para remover",
    anomaly: "anomalia",
    status: {
      total: "{count} descrições",
      forTerm: " para “{term}”",
      refreshing: "atualizando…",
    },
    facet: {
      typology: "Tipologia",
      subject: "Assunto",
      entityType: "Tipo de entidade",
      level: "Nível de descrição",
    },
    dateRange: {
      title: "Data",
      from: "de",
      to: "até",
      clear: "limpar datas",
    },
    /**
     * The chips of the filters that are set. `entity`, `from` and `to` carry the value; the facet
     * prefix and the raw id are completed by the screen, which owns the fallback.
     */
    filters: {
      entity: "Entidade {value}",
      level: "Nível",
      ancestor: "Dentro de um ramo do arranjo",
      onlyAnomalies: "Somente anomalias",
      onlyWithoutAnomaly: "Somente sem anomalia",
      from: "De {date}",
      to: "Até {date}",
    },
    empty: {
      title: "Nenhuma descrição encontrada",
      hintFiltered: "Há filtros ativos. Remova um deles para ampliar a busca.",
      hintEmpty: "O acervo pode ainda não estar materializado nem revisado — veja a página inicial.",
    },
  },
  typologies: {
    status: "{total} tipologias · {active} ativas · {classified} descrições classificadas",
    catalogTitle: "Catálogo",
    notice:
      "O nome é o rótulo que o classificador propõe; a descrição de contexto é {documentation} e não chega à classificação. Aposentar uma tipologia a retira das opções do classificador {without} desclassificar nenhuma descrição — por isso a contagem de cada uma continua visível.",
    /** The two emphasised halves of the notice, so the sentence translates as one string. */
    noticeDocumentation: "documentação para quem lê o catálogo",
    noticeWithout: "sem",
    queue: {
      title: "Recusas do classificador",
      waiting: "{count} aguardando tipologia",
      hint: "O classificador examinou estas descrições e não teve confiança suficiente para escolher uma tipologia. As que chegaram mais perto de ser classificadas vêm primeiro. Classificar aqui salva a escolha, registra a revisão e marca a descrição como aprovada por uma pessoa — o classificador não a altera depois. Se nenhuma tipologia serve, crie ou reative uma no catálogo abaixo.",
      emptyTitle: "Nenhuma recusa pendente",
      emptyHint:
        "Isso não quer dizer que o catálogo cobre o acervo: quer dizer que nenhuma descrição tem uma recusa aberta do classificador. Uma descrição que já recebeu tipologia sai daqui, e uma que o classificador nunca examinou não entra — a recusa só é registrada quando a classificação é feita e fica abaixo da confiança mínima.",
    },
    refusal: {
      confidenceTitle:
        "A confiança que o classificador teve antes de recusar. Abaixo da confiança mínima, a decisão é sua.",
      noConfidence: "sem confiança registrada",
      confidence: "confiança {score}",
      guess: "palpite:",
      retiredSuffix: " (aposentada)",
      noGuess: "sem palpite registrado",
      selectAria: "Tipologia de {title}",
      choose: "Escolha uma tipologia…",
      classifying: "Classificando…",
      classify: "Classificar",
      open: "Abrir ficha",
    },
    card: {
      editToggle: "Editar esta tipologia",
      active: "ativa",
      retired: "aposentada",
      countTitle: "Descrições classificadas com esta tipologia",
      retireTitle: "Sai das opções do classificador; as descrições já classificadas mantêm a tipologia.",
      reactivateTitle: "Volta a ser uma opção do classificador.",
      nameField: "Nome (o rótulo do classificador)",
      contextField: "Descrição de Contexto (o que entra nesta tipologia; só o arquivista lê)",
      unsaved: "alterações não salvas",
    },
    create: {
      trigger: "+ Nova tipologia",
      toggle: "Criar uma tipologia",
      hint: "Serve quando o acervo tem uma forma documental que o classificador não propõe; o nome é o rótulo que ele usa.",
      warning:
        "O classificador recebe {onlyName}. Um nome comprido ou uma frase fazem a classificação perder o vínculo com o texto e rotular tudo com a mesma tipologia: prefira a forma diplomática curta (Ata de Reunião, Ofício, Planta) e deixe os exemplos na descrição de contexto.",
      onlyName: "só o nome",
      name: "Nome",
      namePlaceholder: "ex.: Ata de Reunião",
      context: "Descrição de Contexto",
      contextPlaceholder: "ex.: registros de encontros e deliberações",
      submit: "{verb} tipologia",
    },
  },
};

export const en: typeof pt = {
  collection: {
    mode: {
      lexical: "Keyword",
      semantic: "By Meaning",
      hybrid: "Combined Search",
    },
    modeTitle: {
      lexical: "Keyword Search",
      semantic: "Meaning Search",
      hybrid: "Combined Search",
    },
    notice: {
      lexical:
        "{title}: Finds exactly the words you typed. Ideal when you already know the title, code or specific term.",
      semantic:
        "The {title} finds documents by context, even when they do not contain the exact word. If you know the exact term, keyword search is usually faster.",
      hybrid:
        "The {title} combines the best of both: it finds exact terms and understands the meaning of the text. It is the recommended option for finding what you need without worrying.",
    },
    searchPlaceholder: "Search the collection…",
    clearSearch: "Clear search",
    clearFilters: "Clear filters",
    removeFilter: "Click to remove",
    anomaly: "anomaly",
    status: {
      total: "{count} descriptions",
      forTerm: " for “{term}”",
      refreshing: "refreshing…",
    },
    facet: {
      typology: "Typology",
      subject: "Subject",
      entityType: "Entity type",
      level: "Description level",
    },
    dateRange: {
      title: "Date",
      from: "from",
      to: "to",
      clear: "clear dates",
    },
    filters: {
      entity: "Entity {value}",
      level: "Level",
      ancestor: "Inside an arrangement branch",
      onlyAnomalies: "Only anomalies",
      onlyWithoutAnomaly: "Only without an anomaly",
      from: "From {date}",
      to: "Until {date}",
    },
    empty: {
      title: "No description found",
      hintFiltered: "There are active filters. Remove one to broaden the search.",
      hintEmpty: "The collection may not be materialised or reviewed yet — see the home page.",
    },
  },
  typologies: {
    status: "{total} typologies · {active} active · {classified} descriptions classified",
    catalogTitle: "Catalogue",
    notice:
      "The name is the label the classifier proposes; the context description is {documentation} and does not reach classification. Retiring a typology removes it from the classifier's options {without} unclassifying any description — which is why each one's count stays visible.",
    noticeDocumentation: "documentation for whoever reads the catalogue",
    noticeWithout: "without",
    queue: {
      title: "Classifier refusals",
      waiting: "{count} awaiting a typology",
      hint: "The classifier examined these descriptions and did not have enough confidence to choose a typology. Those that came closest to being classified come first. Classifying here saves the choice, records the revision and marks the description as approved by a person — the classifier does not change it afterwards. If no typology fits, create or reactivate one in the catalogue below.",
      emptyTitle: "No pending refusal",
      emptyHint:
        "This does not mean the catalogue covers the collection: it means no description has an open refusal from the classifier. A description that already received a typology leaves here, and one the classifier never examined does not enter — the refusal is only recorded when classification runs and falls below the minimum confidence.",
    },
    refusal: {
      confidenceTitle: "The confidence the classifier had before refusing. Below the minimum confidence, the decision is yours.",
      noConfidence: "no confidence recorded",
      confidence: "confidence {score}",
      guess: "guess:",
      retiredSuffix: " (retired)",
      noGuess: "no guess recorded",
      selectAria: "Typology for {title}",
      choose: "Choose a typology…",
      classifying: "Classifying…",
      classify: "Classify",
      open: "Open the dossier",
    },
    card: {
      editToggle: "Edit this typology",
      active: "active",
      retired: "retired",
      countTitle: "Descriptions classified with this typology",
      retireTitle: "Leaves the classifier's options; descriptions already classified keep the typology.",
      reactivateTitle: "Becomes an option for the classifier again.",
      nameField: "Name (the classifier's label)",
      contextField: "Context Description (what belongs to this typology; only the archivist reads it)",
      unsaved: "unsaved changes",
    },
    create: {
      trigger: "+ New typology",
      toggle: "Create a typology",
      hint: "It is useful when the collection has a documentary form the classifier does not propose; the name is the label it uses.",
      warning:
        "The classifier receives {onlyName}. A long name or a sentence makes classification lose the link with the text and label everything with the same typology: prefer the short diplomatic form (Meeting Minutes, Official Letter, Plan) and leave the examples in the context description.",
      onlyName: "only the name",
      name: "Name",
      namePlaceholder: "e.g.: Meeting Minutes",
      context: "Context Description",
      contextPlaceholder: "e.g.: records of meetings and deliberations",
      submit: "{verb} typology",
    },
  },
};
