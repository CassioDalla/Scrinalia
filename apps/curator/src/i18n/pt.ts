/**
 * The Portuguese catalogue: the source of the interface's copy (ADR 0020).
 *
 * Portuguese is canonical here, unlike the documentation: the person doing the work reads it first,
 * so a missing English string must fail the build instead of falling back to this one. `en.ts` is
 * typed as this object, which is the gate.
 *
 * A message is a string with `{name}` placeholders; the `Trans` component renders the markup the
 * placeholder carries. The screens hold keys, never copy.
 */

import type { ScreenId } from "@/lib/screens";
import { pt as tagsPt } from "@/i18n/pages/tags";
import { pt as documentPt } from "@/i18n/pages/document";
import { pt as entitiesPt } from "@/i18n/pages/entities";
import { pt as conflictsPt } from "@/i18n/pages/conflicts";
import { pt as runsPt } from "@/i18n/pages/runs";
import { pt as workerPanelPt } from "@/i18n/pages/workerPanel";
import { pt as exclusionsPt } from "@/i18n/pages/exclusions";
import { pt as browseAPt } from "@/i18n/pages/browseA";
import { pt as browseBPt } from "@/i18n/pages/browseB";
import { ATTRIBUTION } from "@/lib/attribution";

/** The copy of one screen: the menu entry, the header's subtitle and, where it has one, the sentence. */
type ScreenCopy = {
  label: string;
  hint: string;
  description?: string;
};

const screens: Record<ScreenId, ScreenCopy> = {
    inbox: {
      label: "Início",
      hint: "O que precisa de mim hoje",
      description: "Cada cartão leva à tela que resolve a pendência, já filtrada.",
    },
    collection: {
      label: "Lista e Busca",
      hint: "Facetas e Filtros",
      description: "Busca por Palavra-chave, Significado ou Busca Combinada do acervo.",
    },
    tree: {
      label: "Árvore",
      hint: "Hierarquia do Acervo",
      description:
        "Navegação pelo arranjo materializado. Escolher um nó mostra o ramo e as descrições que ele contém.",
    },
    deletions: {
      label: "Histórico de exclusões",
      hint: "Registro de itens removidos",
      description:
        "Consulta dos dados originais de registros excluídos em definitivo, preservados apenas para fins de histórico e auditoria.",
    },
    diagnostics: {
      label: "Diagnóstico do Arranjo",
      hint: "Onde está incoerente",
      description:
        "Onde o acervo está incoerente. Nenhuma correção acontece sozinha: cada linha mostra a evidência e leva ao lugar onde se decide.",
    },
    tags: {
      label: "Tags",
      hint: "Uso, Termos Duplicados, Mesclagem",
      description: "Gerencie a relevância das etiquetas, identifique duplicidades e mescle termos semelhantes.",
    },
    categories: {
      label: "Categorias",
      hint: "Organização dos Assuntos",
    },
    discover: {
      label: "Descobrir Categorias",
      hint: "Agrupamentos por tema",
      description: "Agrupa o vocabulário por tema para achar o assunto que ainda não foi classificado.",
    },
    subjectExclusions: {
      label: "Não é Assunto",
      hint: "O que a classificação não deve adivinhar",
      description:
        "O veredito de significado: a classificação de assunto deixa de adivinhar estes termos. Confirmar aqui também bane a grafia, mas não exclui a Tag do acervo.",
    },
    blockedSpellings: {
      label: "Grafias bloqueadas",
      hint: "O que não pode virar tag de novo",
      description:
        "As grafias que o extrator não pode recriar como tag, no eixo em que foram bloqueadas — e a exclusão das tags que já existem com esses nomes.",
    },
    entities: {
      label: "Entidades Nomeadas (NER)",
      hint: "Relevância, Tipo e Mesclagem",
      description:
        "Revise a relevância dos termos, defina a categoria (pessoa, local ou instituição) e junte nomes repetidos.",
    },
    nerExclusions: {
      label: "Remover de Entidades",
      hint: "Isto é assunto, não nome",
      description: "Classificar como termo temático (assunto) em vez de pessoa, local ou entidade coletiva.",
    },
    conflicts: {
      label: "Conflitos",
      hint: "Assunto x Nome Próprio",
    },
    textTemplates: {
      label: "Trechos",
      hint: "Boilerplate e escopo",
    },
    cleaningRules: {
      label: "Regras",
      hint: "Reescrever ou sinalizar",
    },
    anomalies: {
      label: "Anomalias",
      hint: "O que o validador marcou",
    },
    plan: {
      label: "Plano de arranjo",
      hint: "Decidir os níveis",
    },
    levels: {
      label: "Níveis de descrição",
      hint: "A escada NOBRADE",
    },
    typologies: {
      label: "Tipologias",
      hint: "A forma diplomática",
    },
    vocabulary: {
      label: "Vocabulário do acervo",
      hint: "Nomes e lugares deste acervo",
    },
    workers: {
      label: "Workers e execuções",
      hint: "O que roda e o que rodou",
      description:
        "O painel do que está rodando agora — preset, modelo, fila, última e execução ativa — e o histórico do que já rodou, na aba ao lado.",
    },
    origins: {
      label: "Origens",
      hint: "Configurar, pausar e agendar",
      description:
        "As fontes que esta instalação lê, com a fila, a agenda e a configuração de cada uma; a entrada manual e a importação CSV ficam no Acervo, em Nova Descrição.",
    },
    newDescription: {
      label: "Nova Descrição",
      hint: "Digitar ou importar CSV",
      description: "Crie uma descrição manualmente ou importe um CSV.",
    },
    workerSettings: {
      label: "Configuração dos Workers",
      hint: "Motor, preset e o histórico",
      description:
        "O padrão salvo de cada worker — motor, preset, lote e opções — e quem alterou o quê, execução após execução.",
    },
    health: {
      label: "Saúde do sistema",
      hint: "Banco, modelos, storage e origens",
      description:
        "Banco, modelos do Ollama, storage de miniaturas, origens da ingestão e a configuração efetiva do processo.",
    },
    settings: {
      label: "Configurações",
      hint: "Contas, catálogos e operação",
      description: "As telas que se decidem uma vez, longe da curadoria do dia a dia.",
    },
    users: {
      label: "Usuários",
      hint: "Contas, papéis e sessões",
    },
    dossier: {
      label: "Descrição",
      hint: "O dossiê de uma descrição",
    },
};

export const pt = {
  product: {
    tagline: "Curadoria do acervo",
    documentTitle: `${ATTRIBUTION.name} — Curadoria`,
  },
  common: {
    nothingFound: "Nada encontrado",
    readingDescriptions: "Lendo as descrições…",
    next: "Próxima →",
    previous: "← Anterior",
    range: "{from}–{to} de {total}",
    readingDescription: "Lendo a descrição…",
    edit: "Editar",
    close: "fechar",
    ledgerSearch: "Buscar no histórico…",
    ledgerEmpty: "Nenhum resultado para “{term}”",
    ledgerEmptyHint: "Há {count} {noun} no histórico, mas nenhum corresponde ao termo.",
    seeMore: "Ver mais {count}",
    showingFiltered: "Mostrando {shown} de {matched} que correspondem a “{term}” ({total} no total)",
    showing: "Mostrando {shown} de {matched} ({total} no total)",
    footerFiltered: "{matched} de {total} {noun}",
    footer: "{total} {noun}",
    closeAction: "Fechar",
    notInformed: "— não informado —",
  },
  pages: {
    ...runsPt,
    ...workerPanelPt,
    ...exclusionsPt,
    ...browseAPt,
    ...browseBPt,
    cleaningRules: {
      activeOne: "1 regra ativa",
      activeMany: "{count} regras ativas",
      none: "Nenhuma regra ativa",
      retiredOne: "1 aposentada",
      retiredMany: "{count} aposentadas",
      notice:
        "O tipo da regra é o que separa limpar de destruir. Uma regra que reescreve o texto substitui cada ocorrência no acervo; uma que só sinaliza, ou que consulta o modelo, apenas aponta o problema, sem tocar no texto. Regras nunca são excluídas: as aposentadas continuam nesta tela, com o botão de reativar.",
      emptyTitle: "Nenhuma regra ativa",
      emptyHint:
        "Sem nenhuma regra ativa que reescreva o texto, nada no acervo é reescrito. Sem nenhuma regra ativa que sinalize, nenhuma ocorrência é marcada pelas suas regras; as anomalias que o sistema aponta por conta própria — sem data, título vazio — continuam aparecendo. As aposentadas ficam abaixo, com o botão de reativar.",
      activeBadge: "ativa",
      retiredBadge: "aposentada",
      expression: "expressão:",
      replacesBy: "substitui por:",
      emptyValue: "(vazio)",
      anomalyReason: "motivo da anomalia:",
      engine: "engine:",
      rewriteWarning:
        "Esta regra reescreve o acervo: cada ocorrência em {column} será substituída na próxima varredura. As descrições aprovadas por uma pessoa não são tocadas.",
      retiredNote:
        "Aposentada: esta regra não é aplicada ao acervo. Reativar devolve a mesma regra — nada foi excluído.",
      newRule: "+ Nova regra",
      newRuleTitle: "Nova regra",
      newRuleHint:
        "Uma regra que reescreve substitui cada ocorrência no acervo inteiro e só é salva depois de conferir o impacto.",
      nameField: "Nome",
      namePlaceholder: "ex.: normaliza abreviação de logradouro",
      targetField: "Campo da Descrição",
      regexField: "Expressão Regular (Python)",
      replacementField: "Substituir por (vazio = remover o trecho)",
      kindField: "Tipo",
      anomalyField: "Motivo Registrado no Documento quando Casar",
      anomalyPlaceholder: "ex.: título fora do padrão",
      engineField: "Motor",
      engineDefault: "padrão ({engine})",
      noEngine: "nenhum motor",
      loading: "carregando…",
      engineHint: "Em branco, a regra usa o motor padrão. Só é possível salvar com um motor desta lista.",
      presetField: "Preset",
      noPreset: "sem preset (o padrão do motor)",
      saveActivate: "Salvar e ativar",
      previewFirst: "Confira o impacto antes: esta regra reescreve o acervo",
      previewHint: "uma regra que reescreve só é salva depois de conferir o impacto",
      sampleFound: "A amostra encontrou {count} descrições que mudariam em {column}.",
      invalidRegex: "Expressão inválida: {error}",
      regexUnreadable: "a expressão não pôde ser lida.",
    },
    ...tagsPt,
    ...documentPt,
    ...entitiesPt,
    ...conflictsPt,
    anomalies: {
      emptyTitle: "Nenhuma anomalia detectada",
      emptyHint:
        "Pode ser que o acervo não tenha nenhum dos defeitos que a verificação procura, ou que ela ainda não tenha rodado. Regras que só sinalizam acrescentam outros motivos. Veja as {link}.",
      cleaningRulesLink: "regras de limpeza",
      reasonsFound: "motivos encontrados:",
      fixHint:
        "Corrigir é revisar a ficha: a edição fica no histórico e marca a descrição como revisada por humano; a partir daí a IA não a sobrescreve.",
      status: "{count} descrições com anomalia",
      reasonHint: "Motivo registrado pelo validador de qualidade",
      rules: "Regras",
    },
    inbox: {
      countsGenerated: "Contagens geradas em {date}.",
      notReadyTitle: "Esta tela ainda não está pronta para uso.",
      notReady: "tela em preparação",
      empty: "nada pendente",
      open: "abrir →",
      emptyTitle: "Nenhuma pendência recebida",
      emptyHint:
        "Nada chegou, o que não quer dizer que o acervo esteja em ordem. Avise quem administra a instalação.",
    },
    settings: {
      emptyTitle: "Nada para configurar",
      emptyHint:
        "Os cartões desta página são as telas de configuração da instalação (contas, catálogos, arranjo e operação), e o seu papel não alcança nenhuma delas. Por isso a entrada Configurações não aparece no menu.",
    },
    csvImport: {
      title: "Importação CSV",
      downloadTemplate: "Baixar Modelo",
      intro:
        "Arraste ou selecione sua planilha. O sistema lê os dados na hora para conferir se está tudo certo antes de enviar para a sua central de revisão.",
      fileLabel: "Arquivo CSV",
      fileHint: "Até {rows} linhas e {mb} MB. A primeira linha é o cabeçalho.",
      delimiter: "Separador",
      comma: "Vírgula",
      semicolon: "Ponto e vírgula",
      commaLower: "vírgula",
      semicolonLower: "ponto e vírgula",
      fileSummary: "{file} · separador {delimiter}",
      fileSummaryWithEncoding: "{file} · {encoding} · separador {delimiter}",
      noFile: "Nenhum arquivo preparado.",
      readError: "Não foi possível ler o arquivo.",
      idSuffix: " · identificador",
      outsideMap: " · fora do mapa",
      aboutColumn: "Sobre a coluna {column}",
      unknownColumns: "Estas colunas não fazem parte do mapa e não serão importadas: {columns}.",
      moreProblems: "e mais {count} problemas no arquivo.",
      line: "Linha",
      identifier: "Identificador",
      titleColumn: "Título",
      localPreview: "Prévia local",
      result: "Resultado",
      reason: "Motivo",
      previewOf: "Prévia das 5 primeiras de {count} linhas.",
      warnedLine: "{count} linha(s) com aviso local; a API confirma o resultado de cada uma.",
      importing: "Importando…",
      importRows: "Importar {count} linhas",
      importAction: "Importar",
      fixBefore: "Corrija o arquivo antes de enviar.",
      fileTooLarge: "O arquivo tem {mb} MB; o limite é {limit} MB. Divida-o em partes.",
      dossierNote:
        "O dossiê só encontra o registro depois que a transferência rodar; até lá, ele ainda não aparece no acervo e a revisão por IA não começou.",
      accepted: "Aceita",
      duplicated: "Duplicada",
      invalid: "Inválida",
    },
    users: {
      status: "{accounts} contas · {active} ativas",
      notice:
        "A senha criada aqui é temporária: a conta troca a senha no primeiro acesso, antes de chegar às telas. Desativar uma conta encerra todas as sessões dela na hora. A última conta de administrador ativa não pode ser desativada nem ter o papel trocado — promova outra antes. Várias tentativas de acesso falhas bloqueiam a conta por um tempo que dobra a cada novo bloqueio, até um limite; redefinir a senha destrava a conta e encerra as sessões dela.",
      newAccount: "+ Nova conta",
      createTitle: "Criar uma conta",
      createHint:
        "O papel decide o que a conta alcança. A senha é temporária e precisa ter o tamanho mínimo da instalação; não pode ser o próprio e-mail.",
      email: "E-mail",
      name: "Nome",
      role: "Papel",
      tempPassword: "Senha temporária",
      emailPlaceholder: "nome@instituicao.org",
      createButton: "Criar conta",
      created: "Conta {email} criada.",
      editAccount: "Editar esta conta",
      activeBadge: "ativa",
      inactiveBadge: "desativada",
      selfBadge: "você",
      mustChangeTitle: "Ainda usa a senha temporária",
      mustChangeBadge: "troca pendente",
      lockedTitle: "Bloqueada por tentativas de acesso: a senha correta também é recusada até o prazo.",
      lockedBadge: "bloqueada até {date}",
      failedTitle: "Tentativas de acesso falhas desde o último acesso bem-sucedido",
      failedBadge: "tentativas de acesso falhas: {count}",
      lastLogin: "último acesso: {date}",
      never: "nunca",
      resetPassword: "Redefinir senha",
      resetHint:
        "Redefinir a senha encerra todas as sessões desta conta. É o caminho quando alguém perdeu o acesso.",
      selfNotice:
        "Esta é a sua conta: redefinir a senha aqui encerra a sua própria sessão e desconecta você. Para trocar a senha sabendo a atual, use Trocar senha, no rodapé do menu — com o menu recolhido, o ícone de chave —, que mantém esta sessão aberta.",
      newTempPassword: "Nova senha temporária",
      mustChangeCheck: "exigir troca no próximo acesso",
      resetting: "Redefinindo…",
      sessionsTitle: "Sessões ativas",
      revokeAll: "Encerrar todas",
      revoking: "Encerrando…",
      noSessions: "Nenhuma sessão ativa.",
      unknownBrowser: "navegador não informado",
      lastUsed: "último uso em {date}",
      thisSession: "esta sessão",
      end: "Encerrar",
    },
    materialisation: {
      decision: "Decisão",
      decidedOf: "de {total} degraus decididos",
      onlyApproved:
        "Só os degraus aprovados entram na árvore. Um degrau rejeitado deixa suas descrições órfãs de propósito: elas ficam no degrau aprovado mais próximo acima.",
      materialise: "Materializar",
      notePlaceholder: "Nota da decisão (opcional)",
      noApproved: "Nenhum degrau aprovado: aprove ao menos um antes de materializar a árvore.",
      previewFirst: "Confira o impacto antes de materializar.",
      materialising: "Materializando…",
      nothingWritten: "Nada foi escrito ainda: estes números são exatamente o que a materialização vai fazer.",
      nodesToCreate: "degraus a criar",
      nodesToAdopt: "degraus a reaproveitar",
      alreadyInTree: "já na árvore",
      documentsToAttach: "descrições a vincular",
      documentsPlaced: "descrições já no lugar",
      remainingOrphans: "descrições que continuam órfãs",
      rootedEarly: "{count} degrau(s) ficariam na raiz: o degrau acima deles não foi aprovado.",
      seeAll: "Ver os {count} degraus",
      resultLine:
        "Materialização {id}: {created} degrau(s) criado(s), {adopted} reaproveitado(s), {attached} descrição(ões) ligada(s).",
      resultNote:
        "Cada materialização fica registrada no histórico abaixo, com o estado anterior do que mudou. Desfazer recoloca as descrições onde estavam e remove os degraus criados; se uma materialização posterior tiver ligado algo a eles, o desfazer recusa.",
      undoThis: "Desfazer esta materialização",
      undoing: "Desfazendo…",
      historyTitle: "Histórico de materializações",
      logPlaceholder: "Buscar por quem materializou ou pela nota…",
      readingHistory: "Lendo o histórico…",
      emptyTitleTerm: "Nenhuma materialização para “{term}”",
      emptyTitleNone: "Nenhuma materialização ainda",
      emptyHintTerm: "A busca cobre quem materializou e a nota da decisão.",
      emptyHintNone: "Cada materialização fica registrada aqui, com o estado anterior do que mudou.",
      undoneAt: "desfeita em {date}",
      changedRows: "{date} · {count} registro(s) alterado(s)",
      byAuthor: " · por {name}",
      seeMore: "Ver mais",
      showing: "mostrando {shown} de {total} {noun}",
      foundBySearch: "materialização(ões) encontrada(s) pela busca",
      allMaterialisations: "materialização(ões)",
    },
    newDescription: {
      typeTab: "Digitar",
      csvTab: "Importar CSV",
      noCategory: "sem categoria",
      accessPlaceholder: "Busque uma tag ou digite um termo novo",
      accessAdd: "Adicionar “{term}”",
      accessRemove: "Remover {name}",
      accessSearching: "Buscando…",
      accessSearchFailed: "Não foi possível buscar no catálogo. Pressione Enter para usar o termo digitado.",
      accessDuplicate: "“{term}” já está na lista.",
      accessPreviewFailed: "Não foi possível conferir os pontos de acesso; eles serão enviados como digitados.",
      dropped: "“{label}” {reason} e será descartado.",
      reasonStopword: "é um termo bloqueado",
      reasonTooShort: "é curto demais (mínimo de 3 caracteres)",
      reasonTooLong: "é longo demais (máximo de 100 caracteres)",
      createdOne: "“{label}” será criado no arquivamento.",
      createdMany: "Serão criados no arquivamento: {labels}.",
      synonym: "“{input}” será ligado a “{name}”.",
      respelled: "“{input}” já está no catálogo como “{name}”.",
      notAllowed: "Sua conta não pode criar descrições. Peça a um curador ou a um administrador da instalação.",
      dateRecorded: "Data registrada: {date}.",
      dateRecordedWithSource: "Data registrada: {date} — como está na fonte: “{expr}”.",
      pendingNote:
        "O registro aparece no acervo quando a transferência rodar. Até lá, o dossiê ainda pode responder “não encontrado”.",
      openDossier: "Abrir o dossiê",
      createBlank: "Criar outra em branco",
      titleLabel: "Título",
      requiredHint: "Campo obrigatório.",
      levelLabel: "Nível de Descrição",
      unclassified: "— não classificado —",
      parentLabel: "Unidade Pai / Superior",
      parentHint: "Selecione o código da unidade à qual esta pertence.",
      parentPlaceholder: "BR PRADAP SMU",
      needsParent:
        "O nível “{level}” pede uma unidade superior. Você pode gravar assim mesmo: o registro entra pendente e o vínculo se faz na aba Arranjo do dossiê.",
      filled: "{count} preenchido(s)",
      openArea: "Abrir a área",
      accessSection: "Pontos de Acesso",
      accessHintShort: "Os assuntos que viraram tags no acervo.",
      accessLabel: "Pontos de Acesso",
      accessFieldHint:
        "Escolha tags do catálogo ou digite termos novos. Termos novos viram tags quando a descrição for arquivada.",
      sourceUrlLabel: "URL da Fonte",
      sourceUrlHint: "Página de onde o registro veio, quando houver.",
      imageUrlLabel: "URL da Imagem",
      imageUrlHint:
        "Se a imagem já está publicada em outro lugar, a cópia para o acervo é feita automaticamente.",
      titleMissing: "Falta preencher o título.",
      formId: "id do formulário: {id}",
    },
    origins: {
      statusNone: "Nenhuma origem configurada",
      statusOne: "{count} origem configurada · {active} ativa(s)",
      statusMany: "{count} origens configuradas · {active} ativa(s)",
      intro:
        "A ingestão lê a origem, guarda o registro bruto e o deixa estruturado, pronto para a transferência. Cada origem tem a sua fila, a sua agenda e a sua configuração.",
      originsTitle: "Origens",
      originsHint:
        "As fontes que esta instalação lê: adicione uma origem disponível, configure, agende, pause e enfileire uma execução.",
      addOrigin: "Adicionar origem",
      emptyTitle: "Nenhuma origem configurada",
      emptyHint:
        "A instalação ainda não lê nenhum site. Adicione uma origem disponível; a entrada manual e a importação CSV ficam no Acervo, em Nova Descrição.",
      allConfigured: "Todas as origens disponíveis já estão configuradas.",
      entriesTitle: "Entradas",
      entriesHint:
        "A entrada manual e a importação CSV não são origens de leitura: o registro é criado no Acervo, e estas linhas só mostram o estado de cada uma.",
      kindManual: "manual",
      kindCsv: "csv",
      kindSite: "site",
      configure: "Configurar",
      scheduleTab: "Agenda",
      viewDetails: "Ver fila, execução e configuração",
      queue: "Fila",
      queueHint: "O que a próxima execução desta origem vai ler.",
      processed: "Processados",
      failedCount: "{count} com erro definitivo",
      noFatal: "sem erro definitivo",
      lastRun: "Última execução",
      none: "nenhuma",
      schedule: "Agenda",
      nextRun: "{tz} · próxima {when}",
      noSchedule: "sem agenda",
      operatorOnly: "Configuração, agenda e execução ficam com o operador.",
      running: "em execução",
      queueWillRun: "a fila vai andar",
      queueWillWait: "a fila vai esperar",
      activeBadge: "ativa",
      pausedBadge: "pausada",
      noOwnConfig: "Sem configuração própria: a origem usa os valores da instalação quando existem.",
      saving: "Salvando…",
      pause: "Pausar",
      reactivate: "Reativar",
      pausedOrigin: "Origem pausada",
      alreadyRunning: "Já há uma execução",
      enqueuing: "Enfileirando…",
      enqueueRun: "Enfileirar execução",
      queuedLine: "Execução #{id} na fila; ela ainda não começou.",
      noConfigFields: "Esta origem não tem campos de configuração.",
      scheduledOptions: "Opções da execução agendada",
      saveConfig: "Salvar configuração",
      configSaved: "Configuração salva.",
      cronHint:
        "Cinco campos (minuto, hora, dia do mês, mês, dia da semana), avaliados no fuso indicado. Um período que chega com uma ingestão em andamento é pulado, não enfileirado.",
      scheduleField: "Agendamento",
      timezoneField: "Fuso Horário",
      saveSchedule: "Salvar agenda",
      removeSchedule: "Remover agenda",
      notConfigurable: "não configurável",
      awaitingTransfer: "{count} aguardando transferência.",
      openEntry: "Abrir a entrada",
      addTitle: "Adicionar origem",
      addHint: "Escolha uma origem que ainda não está configurada.",
      addNote: "A origem já vem pronta com o sistema; adicioná-la aqui só a ativa nesta instalação.",
      allAddedTitle: "Todas as origens já estão configuradas",
      allAddedHint: "Não há outra origem de leitura para adicionar.",
      adding: "Adicionando…",
      add: "Adicionar",
    },
    textTemplates: {
      statusEmpty: "Nenhum trecho no filtro atual",
      statusCount: "{count} trechos no filtro atual",
      notice:
        "O escopo é a decisão que importa. Cada trecho diz de qual texto ele sai — vetor, extração de nomes ou título sugerido. Aprovar tudo o que a máquina sugeriu piorou os resultados da busca: o prefixo de título ajudava o título e prejudicava o vetor. Por isso não existe botão de aprovar todos aqui.",
      searchTrigger: "+ Procurar trechos",
      searchToggle: "Procurar trechos repetidos",
      searchHint:
        "A varredura procura blocos repetidos no acervo e registra cada uma como sugestão, sem mexer nos documentos.",
      scanHint:
        "A varredura registra os candidatos como sugestões inativas: nada muda nos documentos antes de você aprovar um escopo.",
      minRatio: "Fração Mínima do Acervo",
      minDocuments: "Documentos Mínimos",
      scanning: "Varrendo…",
      search: "Procurar",
      scannedLine: "{scanned} documentos lidos · {persisted} candidatos registrados.",
      allStatuses: "Todos",
      emptyTitle: "Nenhum trecho neste filtro",
      emptyHint:
        "Faça a procura acima, ou escreva um trecho à mão. Os trechos aparecem aqui conforme o filtro escolhido.",
      documentsBadgeTitle: "Documentos em que o trecho aparece",
      machineSuggested: "sugerido pela máquina",
      humanWritten: "escrito por humano",
      inactive: "inativo",
      variants: "grafias: {list}",
      removeFrom: "Remover de:",
      saveScope: "Salvar escopo",
      approve: "Aprovar",
      reject: "Rejeitar",
      removeTitle: "Remove do catálogo e devolve os documentos afetados à fila",
      requeued: "{count} documentos voltaram à fila.",
      previewSummary: "{affected} de {scanned} documentos mudariam.",
      newTrigger: "+ Escrever trecho",
      newToggle: "Escrever um trecho",
      newHint: "Criar o trecho já o aplica aos documentos; os afetados voltam para a fila.",
      newExplain:
        "Criar o trecho já o aplica, e os documentos afetados voltam para a fila. Por isso o botão de criar só libera depois de conferir o impacto.",
      textPlaceholder: "trecho exato, como aparece nos documentos",
      actionField: "O Que Fazer com Ele",
      replaceWith: "Substituir por",
      replacementPlaceholder: "texto que fica no lugar",
      createApply: "Criar e aplicar",
      queued: "{count} documentos na fila.",
    },
    vocabulary: {
      status: "{arrangement} nomes de arranjo · {terms} termos do acervo ({active} ativos)",
      notice:
        "Estas duas listas são dados do acervo, não regras do sistema. O que pertence à língua portuguesa — rua, avenida, não identificado, 303 anos, um ano solto — não é decisão desta curadoria e não aparece aqui: mudá-lo seria mudar o significado que o sistema dá à palavra. Aposentar um termo não o exclui: ele deixa de ser recusado e pode voltar a ser sugerido como assunto na próxima classificação.",
      arrangementSection: "Vocabulário de arranjo",
      arrangementHint:
        "O nome que a proposta de arranjo sugere para um nível do código de referência. O código inteiro tem precedência sobre o último segmento: BR PRADAP pode ter um nome próprio e SMU o da secretaria.",
      collectionSection: "Termos do acervo",
      collectionHint:
        "O que o acervo carrega e não é assunto. Um lugar continua alcançável pela busca, como entidade do tipo Local; um nome de pessoa é o produtor ou a pessoa retratada, nunca um assunto. É essa diferença que o tipo registra.",
      editName: "Editar este nome",
      retireName: "A proposta deixa de sugerir este nome.",
      reactivateName: "A proposta volta a sugerir este nome.",
      suggestedName: "Nome Sugerido",
      newName: "+ Novo nome",
      createArrangement: "Criar um nome de arranjo",
      segmentHint: "Um segmento do código (SMU) ou o código inteiro (BR PRADAP).",
      segmentField: "Segmento ou Código",
      segmentPlaceholder: "ex.: SMU",
      namePlaceholder: "ex.: SMU - Secretaria Municipal de Urbanismo",
      createNameButton: "Criar nome",
      editTerm: "Editar este termo",
      retireTerm: "O termo deixa de ser recusado como assunto.",
      reactivateTerm: "O termo volta a ser recusado como assunto.",
      tagsBadgeTitle: "Tags com exatamente esta grafia",
      spellingField: "Grafia como Aparece no Acervo",
      kindField: "Tipo",
      newTerm: "+ Novo termo",
      createCollectionTerm: "Criar um termo do acervo",
      termHint: "Uma grafia que o acervo carrega e que não é assunto.",
      spellingFieldShort: "Grafia",
      spellingPlaceholder: "ex.: batel",
      createTermButton: "Criar termo",
      unsaved: "alterações não salvas",
    },
    health: {
      verified:
        "Verificado em {date}. Cada verificação tem seu próprio limite de tempo: um serviço fora do ar aparece como um cartão vermelho, não como uma tela quebrada.",
      responding: "respondendo",
      offline: "fora do ar",
      databaseTitle: "Acervo",
      documents: "{count} descrições",
      tags: "{count} tags",
      entities: "{count} entidades",
      staging: "{count} registros aguardando transferência",
      ollamaTitle: "Modelos (Ollama)",
      addressDefault: "endereço {host} (padrão local)",
      addressConfigured: "endereço {host} (definido na configuração)",
      installedModels: "modelos instalados: {count}",
      requiredModels: "modelos necessários: {list}",
      noRequiredModels: "nenhum modelo é necessário",
      missingModels: "Faltam no servidor: {list}. Uma execução que precise de um deles falha ao carregar o modelo.",
      storageTitle: "Armazenamento das miniaturas",
      configured: "configurado",
      notConfigured: "não configurado",
      endpoint: "endereço {endpoint}",
      noEndpoint: "sem endereço",
      bucket: "espaço de armazenamento {bucket}",
      noBucket: "sem espaço de armazenamento",
      originsTitle: "Origens",
      originsActive: "{enabled} de {total} origens ativas",
      originEnabled: "ativa",
      originPaused: "pausada",
      noOrigins: "nenhuma origem configurada",
      originsNote: "a fila, a agenda e a configuração de cada origem ficam na tela de origens",
      openOrigins: "Abrir origens",
      configTitle: "Configuração em uso",
      logLine: "registros {level}{detailed} em {dir}",
      logDetailed: " · modo detalhado",
      databaseLine: "acervo em {path}",
      ollamaLine: "modelos em {url}",
      storageLine: "armazenamento em {url}",
      scrapeLine: "endereço padrão das origens: {state}",
      defined: "definido",
      notDefined: "não definido",
      secretsLine: "chaves e senhas configuradas: {list}",
      yes: "sim",
      no: "não",
    },
    levels: {
      status: "{levels} níveis · {documents} descrições classificadas",
      normNotice:
        "A norma é o padrão, não a lei. Um nível desconhecido que chega com a importação entra — a descrição fica sem nível e o diagnóstico a lista —, enquanto o arquivista não pode salvar um nível que não existe. Sem essa diferença, um lote inteiro falharia por causa de uma grafia nova.",
      editToggle: "Editar este nível",
      ordinalTitle: "Posição na escada; não é editável depois de criado",
      activeBadge: "ativo",
      retiredBadge: "aposentado",
      documentsBadgeTitle: "Descrições classificadas neste nível",
      nameField: "Nome",
      aliasesField: "Grafias Aceitas (separadas por vírgula)",
      aliasesPlaceholder: "ex.: subsérie, sub-serie",
      descriptionField: "Descrição (o que o arquivista lê)",
      requiresParent: "exige unidade superior",
      allowsChildren: "pode ter filhos",
      unsaved: "alterações não salvas",
      newRung: "+ Novo degrau",
      addRung: "Acrescentar um degrau",
      ordinalFixed: "Cada degrau tem um ordinal fixo: confira a escada antes de escolher o número.",
      ordinalExplanation:
        "O ordinal é a posição na escada: um nível só pode ser filho de outro de ordinal menor, e depois de criado ele não muda — renumerar mudaria a árvore que já foi arrumada com estes números. Um ordinal novo e um código novo criam um degrau novo.",
      ordinalField: "Ordinal",
      codeField: "Código",
      codePlaceholder: "ex.: serie",
      namePlaceholder: "ex.: Série",
      aliasesFieldShort: "Grafias Aceitas",
      descriptionFieldShort: "Descrição",
      createLevel: "Criar nível",
    },
    categories: {
      tabDescriptions: "Descrições",
      newCategory: "+ Nova Categoria",
      createTitle: "Criar uma Categoria",
      createNote: "Uma categoria nova só passa a valer quando o classificador rodar de novo.",
      classifierNote:
        "O classificador percebe sozinho quando o conjunto de categorias muda e classifica as tags outra vez na execução seguinte.",
      namePlaceholder: "nome, ex.: Saúde",
      descriptionPlaceholder: "descrição para o curador (nunca vai para o modelo)",
      activeSection: "Ativas",
      retiredSection: "Aposentadas",
      retiredNote:
        "Saíram do eixo de assunto porque são proveniência e geografia, não assunto. Nunca foram excluídas: ficam marcadas como aposentada, porque excluir uma categoria excluiria o registro de que ela existiu.",
      seeDescriptions: "Ver as descrições desta Categoria",
      activeBadge: "ativa",
      retiredBadge: "aposentada",
      descriptionsBadgeTitle: "Descrições com pelo menos uma tag nesta categoria",
      descriptionsCount: "{count} descrições",
      nameField: "Nome",
      classifierLabelField: "Rótulo que o Modelo Lê (vazio: usa o nome)",
      curatorDescriptionField: "Descrição para o Curador (nunca vai ao modelo)",
      unsaved: "alterações não salvas",
      emptyActiveTitle: "Nenhuma descrição nesta categoria",
      emptyActiveHint:
        "Nenhuma tag desta categoria está ligada a uma descrição ainda. As tags sem categoria de assunto estão na aba Classificar, em Tags.",
      emptyRetiredTitle: "Categoria aposentada e vazia",
      emptyRetiredHint:
        "Ela saiu do eixo de assunto, e o classificador não a propõe mais — por isso nenhuma descrição a carrega. Continua no catálogo, aposentada: excluir uma categoria excluiria o registro de que ela existiu.",
      status: "{active} ativas · {retired} aposentadas · {documents} descrições com categoria",
    },
    discover: {
      currentCategories: "Categorias Atuais",
      groupByTheme: "Agrupar por tema",
      intro:
        "O agrupamento é processado sob demanda e leva poucos segundos. As listas abaixo são apenas sugestões: nenhum termo é alterado no vocabulário sem a sua aprovação.",
      fromTags: "A partir das Tags",
      fromDocuments: "A partir dos Documentos",
      grouping: "Agrupando… (pode levar alguns segundos)",
      propose: "Propor Categorias",
      readColumns: "O agrupamento lê o texto destes campos.",
      defaultColumn: "(padrão)",
      chooseColumn: "Escolha ao menos um campo.",
      emptyTitle: "Nenhuma proposta nova",
      emptyHint: "O agrupamento não encontrou tema novo, ou as propostas já foram descartadas.",
      seeSamples: "Ver as amostras do agrupamento",
      estimates: "{count} estimativas",
      topic: "tema #{id}",
      created: "Criada",
      createCategory: "Criar categoria",
      categoryName: "Nome da Categoria",
      usedOnNextRun: "A categoria só é usada quando a classificação rodar de novo.",
    },
    deletions: {
      notice:
        "Histórico permanente de exclusões. Os itens desta lista foram excluídos em definitivo e não podem ser restaurados. Esta página preserva os dados originais e o responsável pela ação apenas para fins de consulta e auditoria.",
      status: "{count} item(ns) no histórico de exclusões",
      statusTerm: "{count} item(ns) no histórico de exclusões para “{term}”",
      emptyTitleTerm: "Nenhum item excluído encontrado para “{term}”",
      emptyTitleNone: "Nenhum item excluído até o momento",
      emptyHintTerm: "Tente pesquisar por outro termo, código de referência ou ID.",
      emptyHintNone:
        "O acervo não possui registros de exclusão. Quando um item for removido, o histórico completo de dados aparecerá aqui para consulta.",
      recordId: "ID do registro",
      noReference: "Sem código de referência",
      deletedBy: "· Excluído por {name}",
      unknownUser: "usuário não identificado",
      children: "· Continha {count} item(ns) vinculado(s)",
      searchPlaceholder: "Buscar por código, título ou ID...",
      clearSearch: "Limpar busca",
    },
    diagnostics: {
      noLevel: "sem nível",
      codeLabel: "código:",
      counting: "Contando os problemas…",
      emptyTitle: "Nenhuma descrição com este problema",
      emptyHint:
        "O diagnóstico foi feito e não encontrou nada deste tipo. Para o caminho divergente, este é o resultado esperado: quando uma descrição muda de lugar, o caminho de todo o ramo é reescrito de uma vez.",
      openDescription: "Abrir a descrição",
      openPlan: "Abrir o plano de arranjo",
      overlap:
        "As contagens se sobrepõem de propósito: a mesma descrição pode aparecer em mais de um problema — um Dossiê na raiz conta em “{orphan}” e em “{dossier}” — por isso não há um total geral.",
    },
    thumbnail: {
      unavailable: "Imagem indisponível",
      none: "Sem imagem",
      alt: "Imagem da descrição: {title}",
      unavailableHeading: "Imagem Indisponível",
      storedHeading: "Miniatura Armazenada",
      noSourceHeading: "Sem imagem de origem",
      unreadable: "A imagem guardada não pôde ser lida",
      storedCaption: "Guardada no acervo; o dossiê mostra a miniatura, não o arquivo original.",
      noSourceCaption: "A origem deste registro não publica uma imagem; a descrição continua completa sem ela.",
    },
    preview: {
      published: "publicada",
      notPublished: "não publicada",
      data: "Data",
      level: "Nível",
      typology: "Tipologia",
      arrangement: "Arranjo",
      tagsAndCategory: "Tags e Categoria",
      noTags: "Nenhuma tag nesta descrição.",
      anomaly: "anomalia",
      panelLabel: "Prévia de {title}",
      noCategoryTitle: "Esta tag ainda não tem categoria",
      noCategory: "sem categoria",
    },
    workers: { painel: "Painel", execucoes: "Execuções" },
  },
  system: {
    runStatus: {
      QUEUED: "Na fila",
      RUNNING: "Em execução",
      SUCCESS: "Concluída",
      FAILED: "Falhou",
      INTERRUPTED: "Interrompida",
      CANCELLED: "Cancelada",
    },
    failureSource: { WORKER: "execução", API: "requisição" },
    trigger: { API: "painel", CLI: "linha de comando", SCHEDULE: "agenda" },
    unit: {
      origin: "origens",
      staging: "registros importados",
      document: "descrições",
      tag: "tags",
      pair: "pares",
    },
    noModel: "sem modelo",
    batch: "lote {size}",
    dimensions: "{count} dimensões",
    stepsOff: "com etapas desligadas",
    noParameters: "sem parâmetros",
    optionsNotRecorded: "opções não registradas nesta execução",
    optionsExample: 'Informe as opções como um objeto JSON, por exemplo {"force": true}.',
    invalidJson: "JSON inválido.",
  },
  queues: {
    hierarchy_orphans: {
      label: "Arranjo não materializado",
      description: "Descrições que o arranjo ainda não consegue colocar numa cadeia.",
    },
    hierarchy_plans: {
      label: "Níveis aguardando decisão",
      description: "Níveis que a leitura dos códigos de referência propôs.",
    },
    tag_merge_proposals: {
      label: "Propostas de mesclagem de tags",
      description: "Tags com grafias parecidas que aguardam a decisão de mesclar.",
    },
    cross_domain_conflicts: {
      label: "Conflitos entre assunto e entidade",
      description: "Termos que colidem: o mesmo nome é assunto e nome próprio.",
    },
    subject_low_confidence: {
      label: "Assunto com confiança baixa",
      description: "Tags que o classificador não teve confiança para arquivar numa categoria.",
    },
    orphan_subject_tags: {
      label: "Tags sem categoria de assunto",
      description: "Tags sem categoria: nenhum selo de assunto pode ser mostrado para elas.",
    },
    typology_low_confidence: {
      label: "Tipologia com confiança baixa",
      description: "Descrições cuja tipologia o classificador não conseguiu decidir.",
    },
    anomalies: {
      label: "Anomalias detectadas",
      description: "Descrições que o validador de qualidade marcou.",
    },
    unreviewed_documents: {
      label: "Descrições não revisadas",
      description: "Descrições que nenhuma pessoa revisou ainda.",
    },
  },
  vocabulary: {
    termKind: {
      DISTRICT: {
        label: "Bairro",
        hint: "Um bairro: o lugar mais fino que a coleção distingue. O eixo de entidades o carrega.",
      },
      MUNICIPALITY: {
        label: "Município",
        hint: "Um município, inclusive uma cidade estrangeira. O eixo de entidades o carrega.",
      },
      STATE: {
        label: "Estado",
        hint: "Um estado ou província. O eixo de entidades o carrega.",
      },
      REGION: {
        label: "Região",
        hint: "Uma região mais ampla que um município. O eixo de entidades o carrega.",
      },
      COUNTRY: {
        label: "País",
        hint: "Um país que os registros do acervo alcançam. O eixo de entidades o carrega.",
      },
      PERSON: {
        label: "Pessoa",
        hint: "Um nome de pessoa: o produtor ou a pessoa retratada, nunca um assunto.",
      },
    },
  },
  entities: {
    type: {
      PER: { label: "Pessoa", hint: "Nomes de pessoas, inclusive o autor de um documento." },
      ORG: { label: "Organização", hint: "Instituições, empresas e órgãos produtores." },
      LOC: { label: "Local", hint: "Lugares: logradouros, bairros, rios e edificações." },
    },
    origin: {
      HUMAN: {
        label: "confirmada",
        hint: "Uma pessoa associou ou confirmou esta entidade.",
      },
      AI: {
        label: "IA",
        hint: "O extrator propôs esta entidade e ninguém a revisou ainda.",
      },
      UNKNOWN: {
        label: "não rastreada",
        hint: "Vínculo escrito antes de o sistema registrar quem o criou: não dá para atribuir a ninguém.",
      },
    },
    mergeFlag: {
      MEMBER_WITH_DIGITS: {
        label: "membro com número",
        hint: "Algum membro tem número no nome. Pode ser o mesmo nome escrito com e sem o número, ou outro nome: o número não decide.",
      },
      MIXED_TYPES: {
        label: "tipos diferentes",
        hint: "Algum membro tem tipo diferente da canônica. As grafias absorvidas passam a resolver com o tipo da canônica.",
      },
      MEMBER_IS_SYNONYM: {
        label: "membro é grafia absorvida",
        hint: "Algum membro é uma grafia que já foi absorvida por uma mesclagem anterior — o agrupamento pode ser reflexo de uma decisão antiga.",
      },
      ORPHAN_MEMBER: {
        label: "membro sem descrição",
        hint: "Algum membro não está ligado a nenhuma descrição. Absorvê-lo não perde vínculo, mas é o tipo de registro que a purga de órfãs exclui.",
      },
    },
    exclusionSource: {
      JUDGE: {
        label: "juiz de conflitos",
        hint: "O juiz de conflitos concluiu que a grafia pertence ao eixo de assunto, não a nomes próprios.",
      },
      HUMAN: {
        label: "curadoria",
        hint: "Um arquivista decidiu que o termo é assunto; a tag que justifica a decisão fica registrada.",
      },
    },
    conflictWinner: {
      TAG: { label: "o assunto (tag)", hint: "A grafia é assunto. O termo entra nas exclusões de entidades com a tag que o justifica, e o extrator para de devolvê-lo como nome próprio." },
      ENTITY: { label: "a entidade", hint: "A grafia é um nome próprio. O nome da tag é banido do eixo de assunto, e a classificação daquela tag se perde." },
    },
  },
  csv: {
    parse: {
      unclosedQuote: "As aspas de um dos campos não foram fechadas.",
      empty: "O arquivo não tem nada para importar.",
      headerWithoutName: "Uma das colunas do cabeçalho está sem nome.",
    },
    import: {
      headerOnly: "O arquivo tem só o cabeçalho e nenhuma linha de dados.",
      tooManyRows: "O arquivo tem {rows} linhas e o limite é {limit}. Divida o arquivo em partes.",
      missingRequired:
        "Faltam colunas obrigatórias: {columns}. Baixe o modelo para conferir os nomes das colunas.",
      duplicateFields: "Mais de uma coluna preenche o mesmo campo: {fields}. Deixe só uma coluna para cada campo.",
      columnCount: "A linha {line} tem {cells} colunas, mas o cabeçalho tem {headers}.",
      idTooLong: "O identificador aceita no máximo 50 caracteres.",
      duplicateId: "O identificador já aparece na linha {line}. Use um identificador diferente.",
      required: "O campo '{label}' é obrigatório e está em branco.",
      maxLength: "O campo '{label}' aceita no máximo {max} caracteres.",
      fileTooLarge:
        "A importação tem {mb} MB e o limite é {limit} MB. Divida o arquivo em partes.",
    },
  },
  isad: {
    datePlaceholder: "E.g. 1985-03-14, 1980s or a range",
    areas: {
      identity: {
        title: "3.1 Identidade",
        hint: "O que a descrição é: código, nível, datas e dimensão.",
      },
      context: {
        title: "3.2 Contexto",
        hint: "Quem produziu, como o conjunto chegou até aqui e de onde o registro veio.",
      },
      content: {
        title: "3.3 Conteúdo e Estrutura",
        hint: "O que o documento diz e como o conjunto está organizado.",
      },
      access: {
        title: "3.4 Acesso e Uso",
        hint: "Quem pode consultar, como reproduzir e o que é preciso para usar o documento.",
      },
      allied: {
        title: "3.5 Materiais Relacionados",
        hint: "Onde estão os originais e as cópias, e que outras descrições se relacionam com esta.",
      },
      notes: {
        title: "3.6 Notas",
        hint: "Observações gerais e sobre o estado de conservação.",
      },
      control: {
        title: "3.7 Controle da Descrição",
        hint: "Quem descreveu, sob que regras e quando.",
      },
    },
    fields: {
      reference_code: {
        label: "Código de Referência",
        help: "O código que identifica a unidade de descrição no arranjo.",
      },
      document_date: {
        label: "Data do Documento",
        help: "AAAA-MM-DD, ou a expressão como está na fonte (Década de 1980, 1951-1953).",
      },
      dimension_support: {
        label: "Dimensão e Suporte",
        help: "Quantidade e o suporte do material. Ex: 2 folhas; 1 fotografia em papel; 3,5 m de documentos textuais.",
      },
      producers: {
        label: "Produtor(es)",
        help: "Quem produziu o conjunto: a instituição ou a pessoa. A lista sugere nomes das entidades; escolher um copia o nome, sem criar vínculo.",
      },
      admin_bio_history: {
        label: "História Administrativa / Biografia",
        help: "A trajetória da entidade ou pessoa produtora para contextualizar a criação e o uso dos documentos.",
      },
      admin_archival_history: {
        label: "História Arquivística",
        help: "Informações sobre a custódia, proveniência, acumulação, mudanças de propriedade ou alterações na organização do acervo ao longo do tempo.",
      },
      provenance: {
        label: "Procedência",
        help: "Identificação da fonte imediata de aquisição ou transferência do acervo (doador, alienante, recolhedor ou custodiante anterior).",
      },
      scope_content: {
        label: "Âmbito e Conteúdo",
        help: "Síntese do tema central, alcance temporal, funções/atividades representadas e principais entidades ou indivíduos mencionados no acervo.",
      },
      appraisal_destruction: {
        label: "Avaliação e Temporalidade",
        help: "O prazo de guarda e a decisão de eliminação, quando houver.",
      },
      accruals: {
        label: "Incorporações",
        help: "Indica se são esperados acréscimos ou novas entradas de documentos a esta unidade de descrição (acervo aberto ou fechado).",
      },
      arrangement: {
        label: "Sistema de Arranjo",
        help: "Informações sobre a estrutura de organização, plano de classificação e critérios de ordenação interna da unidade de descrição.",
      },
      access_conditions: {
        label: "Condições de Acesso",
        help: "Informações sobre o estatuto legal ou regulamentos que restringem ou autorizam a consulta pública à unidade de descrição.",
      },
      reproduction_conditions: {
        label: "Condições de Reprodução",
        help: "Restrições relativas a direitos autorais, reprodução (cópias, fotografias) ou publicação dos documentos.",
      },
      language_name: {
        label: "Idioma",
        help: "O idioma predominante do documento.",
      },
      physical_characteristics: {
        label: "Características Físicas",
        help: "Informações sobre o estado de conservação, suporte físico e exigências técnicas ou de preservação para a consulta dos documentos.",
      },
      finding_aids: {
        label: "Instrumentos de Pesquisa",
        help: "Referência a guias, inventários, repertórios ou bases de dados que facilitem a localização e o acesso à unidade de descrição.",
      },
      originals_location: {
        label: "Existência e Localização dos Originais",
        help: "Endereço ou instituição detentora da documentação original quando a unidade de descrição for constituída por cópias.",
      },
      copies_location: {
        label: "Existência e Localização de Cópias",
        help: "Informações sobre cópias em outros formatos ou suportes, bem como sua localização ou identificação no acervo.",
      },
      related_units: {
        label: "Unidades de Descrição Relacionadas",
        help: "Referências cruzadas a outras unidades de descrição com as quais este acervo guarda proveniência ou relação temática.",
      },
      publication_notes: {
        label: "Notas de Publicação",
        help: "Referências bibliográficas de publicações baseadas na pesquisa, uso ou reprodução da unidade de descrição.",
      },
      general_notes: {
        label: "Notas Gerais",
        help: "Informações adicionais que não puderam ser incluídas nos campos anteriores da descrição arquivística.",
      },
      conservation_notes: {
        label: "Notas de Conservação",
        help: "Registro de danos, condições de preservação e tratamentos conservativos ou restaurativos aplicados ou requeridos.",
      },
      archivist_notes: {
        label: "Notas do Arquivista",
        help: "Anotações relativas ao trabalho do responsável pela descrição, procedimentos adotados e decisões arquivísticas.",
      },
      rules_conventions: {
        label: "Regras ou Convenções",
        help: "Identificação dos padrões internacionais, nacionais ou institucionais utilizados na elaboração do registro.",
      },
      description_dates: {
        label: "Datas da Descrição",
        help: "Registro cronológico da elaboração, revisão e atualizações da ficha arquivística.",
      },
    },
  },
  hierarchy: {
    planStatus: { SUGGESTED: "Sugerido", APPROVED: "Aprovado", REJECTED: "Rejeitado" },
    planFlag: {
      ORDINAL_INFERRED: {
        label: "nível inferido",
        hint: "O ordinal não veio de nenhum registro existente: é uma proposta, não uma declaração. Decida o nível olhando os níveis já declarados abaixo.",
      },
      RECORD_WITHOUT_DOCUMENTS: {
        label: "registro sem documentos",
        hint: "Existe um registro com este código e nenhuma descrição ligada a ele. Adotá-lo preserva a identidade que já está no acervo.",
      },
      DUPLICATE_REFERENCE_CODE: {
        label: "código duplicado",
        hint: "Mais de um registro usa este código, então não há uma unidade única a adotar: decida qual dos registros é a unidade.",
      },
      NEAR_DUPLICATE_NODE: {
        label: "sósia de outro degrau",
        hint: "Um irmão difere por uma letra (FOTOGRAFIA x FOTOGRAFIAS). A semelhança não decide nada: decida se este degrau existe ou se funde no outro.",
      },
      LEVEL_NOT_ALLOWED_AS_CHILD: {
        label: "nível não cabe sob o pai",
        hint: "O nível proposto não vem depois do nível do pai na escada, e a árvore não aceita criá-lo assim. Funda num degrau existente ou escolha outro nível.",
      },
      MID_CODE_IDENTIFIER: {
        label: "identificador no meio do código",
        hint: "Há um identificador antes do último termo de vocabulário do arranjo: a divisão do código é um palpite.",
      },
      UNPARSED_TAIL: {
        label: "final do código ilegível",
        hint: "O final do código não é só número (ex.: '(1)', '369B'). O código é listado como está, nunca adivinhado.",
      },
      NO_STRUCTURAL_TOKEN: {
        label: "código sem vocabulário",
        hint: "O código não traz nenhum termo do vocabulário de arranjo: não há degrau a propor.",
      },
    },
    planAction: { CREATE: "criar", ADOPT: "adotar", ALREADY: "já está na árvore" },
    issue: {
      ORPHAN: {
        label: "Sem unidade superior",
        hint: "Descrição sem unidade superior cujo nível exige uma, mais as que não têm nível algum e por isso não podem ser julgadas. A correção é materializar o arranjo deste ramo — ou confirmar que ele não tem nenhum degrau aprovado.",
        actionLabel: "Ir para o plano de arranjo",
        actionHint: "O arranjo é materializado a partir dos degraus aprovados.",
      },
      DOSSIER_WITHOUT_PARENT: {
        label: "Dossiê na raiz",
        hint: "O caso nomeado e mais estreito do anterior: um Dossiê — nível que exige unidade superior — parado na raiz.",
        actionLabel: "Ir para o plano de arranjo",
        actionHint: "Um Dossiê exige uma unidade superior: aprove o degrau acima dele.",
      },
      UNKNOWN_LEVEL: {
        label: "Nível não classificado",
        hint: "A importação tolera nível desconhecido de propósito; o arquivista não. Corrija o nível na própria descrição.",
        actionLabel: "Corrigir na descrição",
        actionHint: "Abra a descrição e escolha o nível de descrição na aba Arranjo.",
      },
      PATH_DIVERGENCE: {
        label: "Caminho divergente",
        hint: "O caminho registrado não bate com o da unidade superior. Deve ser sempre zero: o caminho é reescrito por inteiro quando uma descrição muda de lugar. Se aparecer, o caminho foi alterado por fora da movimentação da descrição.",
        actionLabel: "Corrigir na descrição",
        actionHint: "O caminho é reescrito quando a descrição muda de lugar: confira a unidade superior.",
      },
      LEVEL_DEPTH_MISMATCH: {
        label: "Nível e profundidade do código",
        hint: "O nível declarado é minoria naquela profundidade de código. A norma vem da coleção, não do código: um código de cinco partes pode carregar Itens, uma Série e uma Seção ao mesmo tempo.",
        actionLabel: "Corrigir na descrição",
        actionHint: "Revise o nível declarado: ele é minoria naquela profundidade de código.",
      },
    },
    detail: {
      code_depth: "profundidade do código",
      expected_ordinal: "ordinal esperado",
      declared_ordinal: "ordinal declarado",
      path: "caminho atual",
      expected_path: "caminho esperado",
    },
  },
  taxonomy: {
    mergeReason: { TRIGRAM: "grafia parecida", PLURAL: "singular/plural", MIXED: "grafia e plural" },
    reviewFlag: {
      MEMBER_WITH_DIGITS: {
        label: "membro com número",
        hint: "Algum membro tem número no nome. Pode ser a mesma coisa (br-116 / br 116) ou outra (rua / rua 7): o número não decide.",
      },
      WEAK_MEMBER: {
        label: "membro fraco",
        hint: "A semelhança de algum membro com a canônica é baixa; o agrupamento pode estar juntando coisas diferentes.",
      },
      CATEGORY_WOULD_BE_LOST: {
        label: "categoria seria perdida",
        hint: "Um dos membros está numa categoria de assunto que a canônica não tem. Mesclar exclui essa classificação.",
      },
      MEMBER_IS_SYNONYM: {
        label: "membro é grafia absorvida",
        hint: "Algum membro é uma grafia que já foi absorvida por uma mesclagem anterior — o agrupamento pode ser reflexo de uma decisão antiga.",
      },
    },
    proposalStatus: {
      SUGGESTED: "sugerida",
      APPROVED: "aprovada",
      REJECTED: "rejeitada",
      APPLIED: "aplicada",
    },
    stopwordScope: {
      TAG: {
        label: "assunto (tags)",
        hint: "O termo sai do eixo de assunto. A exclusão das tags com esse nome guarda cada uma no registro, com desfazer.",
      },
      ENTITY: {
        label: "entidades nomeadas",
        hint: "O termo sai da extração de nomes próprios. Não afeta tag nenhuma.",
      },
      ALL: {
        label: "os dois eixos",
        hint: "O termo sai dos dois eixos, e a exclusão das tags o alcança.",
      },
    },
    stopwordMatch: {
      TOKEN: {
        label: "a palavra e os nomes que a contêm",
        hint: "Bloqueia a palavra e qualquer nome que a contenha como palavra inteira — é o que pega o nome que o extrator devolve junto com ela (IPTU do Exemplo).",
      },
      EXACT: {
        label: "só a grafia exata",
        hint: "Bloqueia só a palavra inteira. Um nome que apenas começa ou contém a palavra passa: alameda sozinho é ruído, Alameda Cabral é uma rua.",
      },
    },
    stopwordSource: {
      HUMAN: {
        label: "digitado aqui",
        hint: "Alguém digitou esta grafia em Grafias bloqueadas: é um ato deliberado.",
      },
      CONFLICT: {
        label: "veio de um conflito tag × entidade",
        hint: "O termo foi banido ao resolver um conflito entre a tag e a entidade de mesma grafia.",
      },
      EXCLUSION: {
        label: "veio de “não é assunto”",
        hint: "O termo foi banido junto com a decisão “não é assunto”. O desfazer daquela decisão levanta este ban.",
      },
    },
    catalogState: {
      ALL: {
        label: "Todas",
        hint: "Lista completa de termos, ordenados por frequência de uso.",
      },
      PENDING: {
        label: "Sem decisão",
        hint: "Termos pendentes de avaliação manual e automática.",
      },
      NOT_SUBJECT: {
        label: "Não é assunto",
        hint: "Termo marcado manualmente como não sendo assunto. O termo fica bloqueado para novas etiquetas, mas as ocorrências atuais continuam no acervo e localizáveis na busca.",
      },
      LOW_CONFIDENCE: {
        label: "Confiança baixa",
        hint: "Classificação automática inconclusiva. A etiqueta aguarda validação humana, com a pontuação sugerida pelo sistema exibida na linha.",
      },
    },
  },
  quality: {
    ruleKind: {
      REWRITE: {
        label: "reescreve o texto",
        hint: "A regra substitui cada ocorrência pelo texto de substituição. É a única espécie de regra que mexe no acervo.",
      },
      VALIDATE: {
        label: "só sinaliza",
        hint: "A regra não toca no texto: quando a expressão casa, a descrição ganha uma anomalia com o motivo declarado.",
      },
      LLM_CHECK: {
        label: "consulta o modelo",
        hint: "Um modelo de linguagem dá uma opinião sobre o título. Sem uma regra ativa deste tipo, o modelo não é carregado.",
      },
    },
    targetColumn: {
      original_title: "título original",
      scope_content: "âmbito e conteúdo",
      admin_bio_history: "história administrativa",
      provenance: "proveniência",
      archivist_notes: "notas do arquivista",
    },
    templateStatus: { SUGGESTED: "sugerido", APPROVED: "aprovado", REJECTED: "rejeitado" },
    templateAction: { IGNORE: "tirar do texto", REPLACE: "substituir" },
    templateScope: {
      EMBEDDING: {
        label: "busca por significado",
        hint: "O trecho sai do texto usado na busca por significado. É onde o ganho é maior: mais da metade do acervo repetia o mesmo bloco.",
      },
      NER: {
        label: "extração de nomes",
        hint: "O trecho sai do texto que a extração de nomes e o classificador leem.",
      },
      TITLE: {
        label: "título sugerido",
        hint: "O trecho sai do título sugerido. O prefixo 'Registros Fotográficos -' ajuda aqui e atrapalha a busca por significado — por isso os escopos são separados.",
      },
    },
    anomalyReason: {
      MISSING_DATE: { label: "sem data", hint: "" },
      FUTURE_DATE: { label: "data no futuro", hint: "" },
      EMPTY_TITLE: { label: "título vazio", hint: "" },
      ALL_CAPS_TITLE: { label: "título em caixa alta", hint: "" },
      REPEATED_TITLE: { label: "título repetido", hint: "" },
      TITLE_ONLY_TEMPLATE: { label: "título só com trecho de origem", hint: "" },
      SCOPE_ONLY_BOILERPLATE: { label: "âmbito só com texto repetido", hint: "" },
      NO_TAGS: { label: "sem assuntos", hint: "" },
      NO_TYPOLOGY: { label: "sem tipologia", hint: "" },
      NO_ENTITIES: { label: "sem entidades nomeadas", hint: "" },
      RULE_MATCH: {
        label: "regra do arquivista",
        hint: "Uma regra ativa que só sinaliza ou que consulta o modelo casou. O nome da regra vem depois dos dois-pontos e é ele que o filtro usa.",
      },
      LLM_SUSPECT: {
        label: "suspeita do modelo",
        hint: "O modelo achou o título suspeito. O que ele escreveu fica na ficha, não no filtro: uma faceta sobre esse texto teria opções que nunca se repetem.",
      },
    },
    signal: {
      PLACEHOLDER: {
        label: "texto de preenchimento",
        hint: "A importação grava este texto quando o dado não veio: ele não fala de assunto nenhum.",
      },
      YEAR: {
        label: "ano isolado",
        hint: "Um ano solto é uma data, não um assunto — e o modelo chegava a classificá-lo como assunto.",
      },
      MEASURE: { label: "número com unidade", hint: "Número com unidade é medida, não conceito." },
      STREET: {
        label: "logradouro",
        hint: "Logradouro é lugar: não é assunto, e o eixo de entidades carrega o lugar.",
      },
      PERSON: {
        label: "nome de pessoa",
        hint: "Nome de pessoa é produtor ou biografado, não assunto: o eixo de entidades o carrega.",
      },
      RECORDED: {
        label: "decisão registrada",
        hint: "Não segue um formato reconhecível: foi uma decisão de alguém, e essa decisão é o motivo.",
      },
    },
  },
  format: {
    reviewStatus: {
      PENDING_AI: "Aguardando IA",
      AI_APPROVED: "Aprovado pela IA",
      NEEDS_REVIEW: "Precisa de revisão",
      HUMAN_APPROVED: "Revisado por pessoa",
      REJECTED: "Rejeitado",
    },
    /** `formatDate`'s answer for a record that has no date. */
    noDate: "sem data",
    /** The two forms `descricoes` needs; the plural rule is `Intl.PluralRules`. */
    descriptions: { one: "descrição", other: "descrições" },
  },
  producers: {
    placeholder: "Digite o nome ou busque uma entidade",
    searching: "Buscando entidades…",
    empty: "Nenhuma entidade com esse trecho",
    failed: "Não foi possível buscar as entidades agora.",
  },
  notFound: {
    title: "Tela não encontrada",
    hint: "O endereço não corresponde a nenhuma tela do sistema.",
    backHome: "Voltar ao início",
  },
  attribution: {
    license: "Licença",
    source: "Código-fonte",
    version: "Versão da instalação",
  },
  roles: {
    ADMIN: "Administrador",
    CURATOR: "Curador",
    VIEWER: "Leitor",
  },
  shell: {
    expandMenu: "Expandir o menu",
    collapseMenu: "Recolher o menu",
    mainMenu: "Menu principal",
    changePassword: "Trocar senha",
    close: "Fechar",
    signOut: "Sair",
    signingOut: "Saindo…",
    language: "Idioma",
    automatic: "Automático",
    localeFailed: "Não foi possível salvar o idioma.",
  },
  nav: {
    sections: {
      acervo: "Acervo",
      assuntos: "Assuntos",
      entidades: "Entidades",
      qualidade: "Qualidade",
    },
  },
  settingsTabs: {
    arranjo: "Arranjo e catálogos",
    operacao: "Operação",
    acesso: "Acesso",
  },
  errors: {
    requestFailed: "Não foi possível concluir a operação (erro {status}).",
  },
  actions: {
    save: { label: "Salvar", pending: "Salvando…" },
    create: { label: "Criar", pending: "Criando…" },
    remove: { label: "Remover", pending: "Removendo…" },
    confirm: { label: "Confirmar", pending: "Confirmando…" },
    exclude: { label: "Excluir", pending: "Excluindo…" },
    retire: { label: "Aposentar", pending: "Aposentando…" },
    reactivate: { label: "Reativar", pending: "Reativando…" },
    deactivate: { label: "Desativar", pending: "Desativando…" },
    run: { label: "Enfileirar execução", pending: "Enfileirando…" },
    merge: { label: "Mesclar", pending: "Mesclando…" },
    rename: { label: "Renomear", pending: "Renomeando…" },
    apply: { label: "Aplicar", pending: "Aplicando…" },
    preview: { label: "Conferir impacto", pending: "Conferindo…" },
    undo: { label: "Desfazer", pending: "Desfazendo…" },
    ban: { label: "Banir", pending: "Banindo…" },
    unban: { label: "Desbanir", pending: "Desbanindo…" },
    discard: { label: "Descartar", pending: "Descartando…" },
    cancel: { label: "Cancelar" },
    close: { label: "Fechar" },
    recheck: { label: "Verificar de novo", pending: "Verificando…" },
  },
  digitalObject: {
    label: "Objeto Digital",
    hint: "Anexos (imagem, PDF, áudio) ainda não são enviados; o registro guarda a descrição.",
    disabled: "Indisponível por enquanto",
  },
  screens,
  /**
   * The two screens that share a vocabulary, and the sentence that keeps them apart.
   *
   * `subjectExclusions` decides what a term **means** (it is not a subject, so the classifier stops
   * guessing); `blockedSpellings` vetoes a **spelling** (it may not become a tag again). The reader
   * arrives on the second expecting the first, so the notice names the difference and points at the
   * screen that does it; the card that deletes is named here once and read twice — by the notice and
   * by its own header. A message carries `{placeholders}` for the markup the screen supplies
   * (ADR 0020 §2), which is how a link is part of a sentence instead of next to it.
   */
  spellings: {
    notice:
      "Bloquear uma grafia impede que ela volte a virar tag no eixo escolhido e não remove nada do acervo. Bloquear não é o mesmo que dizer que o termo não é assunto — o que faz a classificação parar é {verdict}. A exclusão das tags que já existem com esses nomes fica em {purge}, abaixo.",
    /** The name of the destructive card: the notice above points at it by this same string. */
    purgeCard: "Excluir as tags com esses nomes",
    /** On the verdict screen, the pointer to where the tags are actually deleted. */
    verdictDeleteHint: "A exclusão das tags fica em {blocked}.",
  },
  auth: {
    login: {
      email: "E-mail",
      password: "Senha",
      signIn: "Entrar",
      signingIn: "Entrando…",
      failure: "Não foi possível entrar.",
      forgot: "Esqueci minha senha",
      noMessage:
        "Nenhuma mensagem é enviada por esta tela. Um administrador redefine a sua senha em {settings}, na conta certa.",
      settingsPath: "Configurações → Usuários",
      lastAdmin:
        "Se a conta for a última de administrador ativa e ninguém conseguir entrar, o acesso é recolocado pelo terminal do servidor, por quem opera a máquina (guia de operação).",
    },
    setup: {
      title: "Primeiro acesso da instalação",
      explanation:
        "Esta instalação ainda não tem contas, e a conta de administração só pode ser criada uma vez. Ela administra o sistema e cria as demais em Configurações › Usuários.",
      email: "E-mail",
      name: "Nome",
      password: "Senha",
      confirmation: "Confirmação da Senha",
      mismatch: "As duas senhas não coincidem.",
      failure: "Não foi possível criar a conta.",
      create: "Criar conta",
      creating: "Criando…",
      noRecovery:
        "Não há recuperação de senha por e-mail: guarde esta senha. Se ela for perdida, só quem administra a instalação pode definir outra.",
    },
    password: {
      title: "Trocar senha",
      forced:
        "Esta conta ainda usa a senha temporária do primeiro acesso. Escolha uma senha sua para continuar.",
      voluntary: "As outras sessões desta conta serão encerradas.",
      current: "Senha Atual",
      next: "Nova Senha",
      confirmation: "Confirmação da Nova Senha",
      mismatch: "As duas senhas não coincidem.",
      failure: "Não foi possível trocar a senha.",
      changing: "Trocando…",
      change: "Trocar senha",
      cancel: "Cancelar",
    },
  },
};

/** The shape every locale's catalogue has; `en.ts` is typed as this. */
export type Messages = typeof pt;
