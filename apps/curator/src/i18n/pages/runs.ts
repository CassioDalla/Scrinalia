/**
 * Screen copy merged into `pages` by `i18n/pt.ts` and `i18n/en.ts`; keeping it in its own module
 * is what lets the screen be extracted in a git worktree without touching the central catalogue.
 */

export const pt = {
  runs: {
    previous: "Anteriores",
    next: "Próximas",
    registered: "Execuções registradas: {count}.",
    intro:
      "Toda execução aparece aqui, venha do painel, da agenda ou da linha de comando. O registro guarda a configuração que foi usada — modelo e preset —, então continua legível depois que a configuração padrão mudar.",
    allWorkers: "todas as etapas",
    allOrigins: "todas as origens",
    allStatuses: "todos os estados",
    clearFilters: "Limpar filtros",
    onlyCause: "Só as execuções desta causa",
    seeAll: "Ver todas",
    emptyTitle: "Nenhuma execução registrada",
    emptyHint:
      "Nenhuma execução foi registrada ainda. O botão 'Enfileirar execução', no painel, cria a primeira entrada.",
    originBadge: "origem {code}",
    trialBadge: "ensaio",
    trialBadgeTitle: "Um ensaio compara configurações e não altera o acervo.",
    trialLine: "comparação de configurações · o resultado e a escolha ficam em {settings}",
    settingsLink: "Configurações › {worker}",
    noEngine: "sem modelo",
    requestedBy: "pedido por {name}",
    attempt: "tentativa {attempt}/{max}",
    retryOf: "nova tentativa de #{id}",
    startsAt: "começa em {when}",
    runner: "executor {id}",
    contact: "contato {when}",
    reservedUntil: "reservado até {when}",
    cancelRequested:
      "Cancelamento pedido em {when}. A execução para no fim do lote atual; o que já foi gravado fica.",
    cancelRequestedBy:
      "Cancelamento pedido em {when} por {by}. A execução para no fim do lote atual; o que já foi gravado fica.",
    cancelOpen: "Cancelar execução…",
    cancelNotice:
      "A execução para no fim do lote atual e o que já foi gravado fica. Se ela ainda não começou, é cancelada agora. O lote em curso não é interrompido: a parada acontece entre um lote e o próximo.",
    cancelPending: "Cancelando…",
    cancelConfirm: "Confirmar cancelamento",
    back: "Voltar",
    failuresTitle: "Falhas agrupadas por causa",
    failuresReading: "lendo…",
    failuresCount: "{count} causa(s) nos últimos 30 dias",
    failuresError: "Não foi possível ler as falhas agrupadas.",
    failuresEmpty:
      "Nenhuma falha nos últimos 30 dias. As execuções que falharam e os erros inesperados do sistema aparecem aqui agrupados pela causa, e não um a um.",
    failuresLastAt: "última em {when}",
    failuresReference: "referência: {id}",
    failuresHint:
      "Clique numa causa para ver só as execuções dela. A referência de uma falha é o que identifica o erro no registro do sistema.",
    failuresMore: "Há mais {count} causa(s) nos últimos 30 dias; as mais recentes estão acima.",
  },
  workerOptions: {
    none: "Esta etapa não tem ajustes além do motor e do lote.",
    noColumns: "Não há colunas para escolher nesta opção.",
    listPlaceholder: "separadas por vírgula",
    defaultPlaceholder: "o do sistema",
    options: {
      columns_to_extract: {
        label: "Colunas Lidas pela IA",
        hint: "O texto que a IA lê. Vazio = o padrão do sistema.",
      },
      columns_to_classify: {
        label: "Colunas Lidas pela IA",
        hint: "O texto que a IA lê. Vazio = o padrão do sistema.",
      },
      confidence_threshold: {
        label: "Limite de Confiança",
        hint: "Abaixo dele o resultado é descartado.",
      },
      force: {
        label: "Forçar",
        hint: "Refaz o que já foi processado, e não só o que falta.",
      },
      limit: {
        label: "Limite de Documentos",
        hint: "Vale só para esta execução; não vira padrão.",
      },
      repeat_threshold: {
        label: "Repetições que Caracterizam um Modelo de Ficha",
        hint: "Quantos títulos iguais indicam um modelo de ficha, um título que se repete de uma descrição para outra.",
      },
      llm_confidence: {
        label: "Confiança Mínima da IA",
        hint: "Abaixo dela a opinião da IA sobre o título é ignorada.",
      },
      similarity_threshold: {
        label: "Similaridade Mínima",
        hint: "O quanto os nomes da tag e da entidade precisam se parecer para o caso ser julgado.",
      },
      auto_resolve_threshold: {
        label: "Confiança para Resolver sem Revisão",
        hint: "Abaixo dela o conflito vai para a fila de revisão.",
      },
    },
  },
};

export const en: typeof pt = {
  runs: {
    previous: "Previous",
    next: "Next",
    registered: "Recorded runs: {count}.",
    intro:
      "Every run appears here, whether it came from the panel, the schedule or the command line. The record keeps the configuration that was used — model and preset — so it stays readable after the default configuration changes.",
    allWorkers: "all steps",
    allOrigins: "all origins",
    allStatuses: "all statuses",
    clearFilters: "Clear filters",
    onlyCause: "Only runs with this cause",
    seeAll: "See all",
    emptyTitle: "No recorded runs",
    emptyHint: "No run has been recorded yet. The 'Enqueue run' button in the panel creates the first entry.",
    originBadge: "origin {code}",
    trialBadge: "trial",
    trialBadgeTitle: "A trial compares configurations and does not change the collection.",
    trialLine: "configuration comparison · the result and the choice are in {settings}",
    settingsLink: "Settings › {worker}",
    noEngine: "no model",
    requestedBy: "requested by {name}",
    attempt: "attempt {attempt}/{max}",
    retryOf: "retry of #{id}",
    startsAt: "starts at {when}",
    runner: "runner {id}",
    contact: "contact {when}",
    reservedUntil: "reserved until {when}",
    cancelRequested:
      "Cancellation requested at {when}. The run stops at the end of the current batch; what was already written stays.",
    cancelRequestedBy:
      "Cancellation requested at {when} by {by}. The run stops at the end of the current batch; what was already written stays.",
    cancelOpen: "Cancel run…",
    cancelNotice:
      "The run stops at the end of the current batch and what was already written stays. If it has not started yet, it is cancelled now. The batch in progress is not interrupted: the stop happens between one batch and the next.",
    cancelPending: "Cancelling…",
    cancelConfirm: "Confirm cancellation",
    back: "Back",
    failuresTitle: "Failures grouped by cause",
    failuresReading: "reading…",
    failuresCount: "{count} cause(s) in the last 30 days",
    failuresError: "Could not read the grouped failures.",
    failuresEmpty:
      "No failures in the last 30 days. Runs that failed and unexpected system errors appear here grouped by cause, not one by one.",
    failuresLastAt: "last at {when}",
    failuresReference: "reference: {id}",
    failuresHint:
      "Click a cause to see only its runs. A failure's reference is what identifies the error in the system log.",
    failuresMore: "There are {count} more cause(s) in the last 30 days; the most recent are above.",
  },
  workerOptions: {
    none: "This step has no settings beyond the engine and the batch.",
    noColumns: "There are no columns to choose in this option.",
    listPlaceholder: "comma-separated",
    defaultPlaceholder: "the system default",
    options: {
      columns_to_extract: {
        label: "Columns Read by the AI",
        hint: "The text the AI reads. Empty = the system default.",
      },
      columns_to_classify: {
        label: "Columns Read by the AI",
        hint: "The text the AI reads. Empty = the system default.",
      },
      confidence_threshold: {
        label: "Confidence Threshold",
        hint: "Below it the result is discarded.",
      },
      force: {
        label: "Force",
        hint: "Redoes what was already processed, not only what is missing.",
      },
      limit: {
        label: "Document Limit",
        hint: "Applies to this run only; it does not become a default.",
      },
      repeat_threshold: {
        label: "Repetitions That Mark a Form Template",
        hint: "How many equal titles indicate a form template, a title that repeats from one description to the next.",
      },
      llm_confidence: {
        label: "Minimum AI Confidence",
        hint: "Below it the AI's opinion about the title is ignored.",
      },
      similarity_threshold: {
        label: "Minimum Similarity",
        hint: "How alike the tag and the entity names must be for the case to be judged.",
      },
      auto_resolve_threshold: {
        label: "Confidence to Resolve Without Review",
        hint: "Below it the conflict goes to the review queue.",
      },
    },
  },
};
