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
