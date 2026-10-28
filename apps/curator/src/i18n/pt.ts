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
  format: {
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
