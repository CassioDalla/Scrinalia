/**
 * The screens, named once.
 *
 * Every screen of the SPA is one record here: the path the router declares, the **label** the
 * archivist reads, and the **hint** that says what it decides. The label is the same string in the
 * three places that used to disagree about it — the menu entry, the settings card, and the page's own
 * `<h1>` — which is the whole point of the file. Before it, the menu said `Tags` and the page said
 * "Vocabulário de tags", the card said `Usuários` and the page "Contas", and two different screens
 * were both called "Diagnóstico" (the arrangement one and the machine one, in the same menu).
 *
 * The rule that replaces those divergences is deliberately blunt: **the page's heading is the
 * label.** A screen whose heading needs to be a sentence is a screen whose name is wrong, and the
 * sentence belongs in `hint`/`description`, where the menu can also read it. So the label is short,
 * the hint explains it, and `description` — set only where the page has something `hint` cannot hold
 * — is what the header shows as the subtitle instead.
 *
 * `path` is not decoration: the coverage gate (`testing/unit/curator/test_curator_copy.py`) reads
 * this file and `router.tsx` and fails when the two sets disagree, so a route cannot be added without
 * a name, and a name cannot survive the route it described.
 *
 * `dynamicTitle` is the one escape hatch, and it belongs to a single screen: the dossier's heading is
 * the record's own title, which no table can carry. It exempts that route from the gate's second
 * rule — the one that forbids a route from typing an `<h1>` of its own — and nothing else.
 */

/** The screens the router declares, plus the dossier, whose path carries a parameter. */
export type ScreenId =
  | "inbox"
  | "collection"
  | "tree"
  | "deletions"
  | "diagnostics"
  | "tags"
  | "categories"
  | "discover"
  | "subjectExclusions"
  | "entities"
  | "nerExclusions"
  | "conflicts"
  | "textTemplates"
  | "cleaningRules"
  | "anomalies"
  | "plan"
  | "levels"
  | "typologies"
  | "vocabulary"
  | "workers"
  | "runs"
  | "health"
  | "settings"
  | "users"
  | "dossier";

export type Screen = {
  /** The route's own path, spelled as `router.tsx` spells it, parameter and all. */
  readonly path: string;
  /** The name of the screen: the menu entry, the settings card and the page's `<h1>`. */
  readonly label: string;
  /** What the screen decides. The menu's second line, and the header's subtitle by default. */
  readonly hint: string;
  /**
   * The header's subtitle, where the hint is too short to be one.
   *
   * Set only on the screens that already carried a sentence worth keeping; everywhere else the
   * header falls back to `hint`, so a page cannot end up with a subtitle nobody wrote.
   */
  readonly description?: string;
  /** The dossier only: the heading is the record's title, so `label` is not what is rendered. */
  readonly dynamicTitle?: true;
};

export const SCREENS: Record<ScreenId, Screen> = {
  inbox: {
    path: "/",
    label: "Início",
    hint: "O que precisa de mim hoje",
    description: "Cada cartão leva à tela que resolve a pendência, já filtrada.",
  },
  collection: {
    path: "/acervo/lista",
    label: "Lista e busca",
    hint: "Facetas e ranking",
    description: "Busca lexical e semântica do acervo, com as facetas e o ranking na URL.",
  },
  tree: {
    path: "/acervo/arvore",
    label: "Árvore",
    hint: "Navegar pelo arranjo",
    description:
      "Navegação pelo arranjo materializado. Escolher um nó mostra o ramo e as descrições que ele contém.",
  },
  deletions: {
    path: "/acervo/excluidas",
    label: "Excluídas",
    hint: "A trilha do que saiu",
    description:
      "O retrato do que saiu — código, título, nível e o conteúdo ISAD(G) inteiro — porque a exclusão é definitiva e nada aqui restaura.",
  },
  diagnostics: {
    path: "/arranjo/diagnostico",
    label: "Diagnóstico do arranjo",
    hint: "Onde está incoerente",
    description:
      "Onde o acervo está incoerente. Nenhuma correção acontece sozinha: cada linha mostra a evidência e leva ao lugar onde se decide.",
  },
  tags: {
    path: "/assuntos/tags",
    label: "Tags",
    hint: "Peso, duplicatas e merges",
    description: "Peso, duplicatas e a fila de merges — a decisão é sempre sua, e o merge é reversível.",
  },
  categories: {
    path: "/assuntos/categorias",
    label: "Categorias",
    hint: "As gavetas de assunto",
  },
  discover: {
    path: "/assuntos/descobrir",
    label: "Descobrir gavetas",
    hint: "Clusters por tema",
    description: "Agrupa o vocabulário por tema para achar o assunto que ainda não tem gaveta.",
  },
  subjectExclusions: {
    path: "/assuntos/excecoes",
    label: "Não é assunto",
    hint: "O que a regra não pega",
    description:
      "Os termos que a classificação de assunto não deve adivinhar. Banir não exclui a tag: ela continua no acervo e alcançável pela busca.",
  },
  entities: {
    path: "/entidades/lista",
    label: "Entidades",
    hint: "NER: peso, tipo e merge",
  },
  nerExclusions: {
    path: "/entidades/excecoes",
    label: "Exclusões de NER",
    hint: "Isto é assunto, não nome",
  },
  conflicts: {
    path: "/entidades/conflitos",
    label: "Conflitos",
    hint: "Assunto x nome próprio",
  },
  textTemplates: {
    path: "/qualidade/trechos",
    label: "Trechos",
    hint: "Boilerplate e escopo",
  },
  cleaningRules: {
    path: "/qualidade/regras",
    label: "Regras",
    hint: "Reescrever ou sinalizar",
  },
  anomalies: {
    path: "/qualidade/anomalias",
    label: "Anomalias",
    hint: "O que o validador marcou",
  },
  plan: {
    path: "/arranjo/plano",
    label: "Plano de arranjo",
    hint: "Decidir os níveis",
  },
  levels: {
    path: "/arranjo/niveis",
    label: "Níveis de descrição",
    hint: "A escada NOBRADE",
  },
  typologies: {
    path: "/arranjo/tipologias",
    label: "Tipologias",
    hint: "A forma diplomática",
  },
  vocabulary: {
    path: "/vocabulario",
    label: "Vocabulário do acervo",
    hint: "Nomes e lugares deste acervo",
  },
  workers: {
    path: "/sistema/workers",
    label: "Workers de IA",
    hint: "Presets, filas e execução",
    description: "O que roda, com qual preset e modelo, o que está na fila e o que já rodou.",
  },
  runs: {
    path: "/sistema/execucoes",
    label: "Execuções",
    hint: "O ledger do que rodou",
    description: "Toda execução entra aqui — pela linha de comando ou pelo painel.",
  },
  health: {
    path: "/sistema/diagnostico",
    label: "Saúde do sistema",
    hint: "Banco, modelos e storage",
    description: "Banco, modelos do Ollama, storage de miniaturas e a configuração efetiva do processo.",
  },
  settings: {
    path: "/configuracoes",
    label: "Configurações",
    hint: "Contas, catálogos e operação",
    description: "As telas que se decidem uma vez, longe da curadoria do dia a dia.",
  },
  users: {
    path: "/configuracoes/usuarios",
    label: "Usuários",
    hint: "Contas, papéis e sessões",
  },
  dossier: {
    path: "/acervo/$descriptionId",
    label: "Descrição",
    hint: "O dossiê de uma descrição",
    dynamicTitle: true,
  },
};

/**
 * What the header shows as the subtitle: the sentence when the screen wrote one, the hint otherwise.
 *
 * The fallback is what keeps the header honest on the thirteen screens whose second line is a status
 * count and nothing else: they get the phrase the menu already uses, instead of an empty line or a
 * sentence invented here that no screen asked for.
 */
export function screenSubtitle(id: ScreenId): string {
  return SCREENS[id].description ?? SCREENS[id].hint;
}
