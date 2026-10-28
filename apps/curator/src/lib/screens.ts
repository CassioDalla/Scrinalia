/**
 * The screens, named once.
 *
 * Every screen of the SPA is one record here: the path the router declares and, for the dossier,
 * the fact that its heading is dynamic. **The name and the hint are not here**: they are copy, and
 * the copy lives in the catalogue (`i18n/pt.ts`, `screens`) keyed by this id (ADR 0020 §5). The menu,
 * the settings card and the page's `<h1>` all read that one record — which is still the point of
 * this file: before it, the menu said `Tags` and the page said "Vocabulário de tags", the card said
 * `Usuários` and the page "Contas".
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
  | "origins"
  | "newDescription"
  | "workerSettings"
  | "health"
  | "settings"
  | "users"
  | "dossier";

export type Screen = {
  /** The route's own path, spelled as `router.tsx` spells it, parameter and all. */
  readonly path: string;
  /** The dossier only: the heading is the record's title, so the label is not what is rendered. */
  readonly dynamicTitle?: true;
};

export const SCREENS: Record<ScreenId, Screen> = {
  inbox: { path: "/" },
  collection: { path: "/acervo/lista" },
  tree: { path: "/acervo/arvore" },
  deletions: { path: "/acervo/excluidas" },
  diagnostics: { path: "/arranjo/diagnostico" },
  tags: { path: "/assuntos/tags" },
  categories: { path: "/assuntos/categorias" },
  discover: { path: "/assuntos/descobrir" },
  subjectExclusions: { path: "/assuntos/excecoes" },
  entities: { path: "/entidades/lista" },
  nerExclusions: { path: "/entidades/excecoes" },
  conflicts: { path: "/entidades/conflitos" },
  textTemplates: { path: "/qualidade/trechos" },
  cleaningRules: { path: "/qualidade/regras" },
  anomalies: { path: "/qualidade/anomalias" },
  plan: { path: "/arranjo/plano" },
  levels: { path: "/arranjo/niveis" },
  typologies: { path: "/arranjo/tipologias" },
  vocabulary: { path: "/vocabulario" },
  workers: { path: "/sistema/workers" },
  origins: { path: "/sistema/ingestao" },
  newDescription: { path: "/acervo/nova" },
  workerSettings: { path: "/configuracoes/workers" },
  health: { path: "/sistema/diagnostico" },
  settings: { path: "/configuracoes" },
  users: { path: "/configuracoes/usuarios" },
  dossier: { path: "/acervo/$descriptionId", dynamicTitle: true },
};
