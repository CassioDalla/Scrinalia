/**
 * The words this interface says more than once.
 *
 * The copy of a screen is the screen's own business — "a trilha, não uma lixeira" belongs to the
 * deletions page and nowhere else — but a handful of words are the *system's*: the product's name,
 * and the verb of each action. Those live here, once, because the alternative is the one this file
 * replaced: `Salvar` on one screen and `gravar` on the next, `Rodar agora` and `Executar agora` on
 * two buttons of the same page, and the project's own name typed into `index.html` where no
 * component could see it.
 *
 * Two things are deliberately **not** here:
 *
 * * **The screen labels** are `lib/screens.ts`. They are not loose words: each one is the name of a
 *   route, and the menu, the settings card and the page heading all read the same record.
 * * **The prose of a page.** A parameter, a caveat, the sentence that explains what a table means —
 *   all of that stays beside the screen it describes, where a reader can judge it in context. A
 *   catalogue of 334 sentences would make every page unreviewable and would buy nothing: what
 *   actually drifted was the vocabulary, not the paragraphs.
 *
 * The one rule this file enforces is **one verb per action**. Where two words look like synonyms
 * and are not — a catalogue row is *retired*, an account is *deactivated*, a term is *banned* — the
 * two have their own entry, and the comment says which object each one acts on. Merging those would
 * be a false unification: the archivist reads them as different decisions because they are.
 */

import { ATTRIBUTION } from "@/lib/attribution";

/**
 * The product, as the interface says it.
 *
 * `ATTRIBUTION.name` stays the single definition of the name for the same reason it is the one that
 * satisfies section 7(b) of the license: renaming the project has to be a change to one line, in the
 * file the license obligation already points at. Nothing in the SPA types the name again — not the
 * rail, not the footer, not the browser tab, and `index.html` carries no name at all (the tab title
 * is set from here by `main.tsx`).
 */
export const PRODUCT = {
  /** The display name. Re-exported, never re-typed. */
  name: ATTRIBUTION.name,
  /** What this build of the product is, for the person using it. The rail's second line. */
  tagline: "Curadoria do acervo",
  /** The browser tab. `index.html` boots with the neutral `Curadoria` and `main.tsx` replaces it. */
  documentTitle: `${ATTRIBUTION.name} — Curadoria`,
  /**
   * The system's version, injected at build time from `pyproject.toml` by `vite.config.ts`.
   *
   * It is the **distribution's** version and not `apps/curator/package.json`'s: the API serves the
   * built SPA from the same commit, so one number describes the installation, and a second one
   * would be a thing to keep in step for no reason. `AttributionFooter` is its only reader.
   */
  version: __APP_VERSION__,
} as const;

/**
 * An action and the word for it while it runs.
 *
 * The two are one record on purpose: a screen that says `Salvar` and then `Criando…` is the same
 * defect as one that says `Salvar` and `Gravar`, and pairing them makes it impossible to fix one
 * half. `pending` is optional because a few of these are instant and never render a middle state.
 */
export type Action = { readonly label: string; readonly pending?: string };

/**
 * The verbs, one per action, with the object each one acts on.
 *
 * `retire` and `deactivate` look alike and are not: the first flips `is_active` on a **catalogue
 * row** — a level, a typology, a drawer, a cleaning rule, a collection term — which the API keeps
 * and the screen shows greyed out, because its foreign key is `SET NULL` and deleting it would erase
 * the fact that it existed. The second disables an **account**. A screen that used one word for both
 * would be telling the archivist that a catalogue row and a person leave the system the same way.
 */
export const ACTION = {
  /** Writes an edited row. */
  save: { label: "Salvar", pending: "Salvando…" },
  /** Brings a row into existence. The trigger beside it reads `+ Nova…`/`+ Novo…`. */
  create: { label: "Criar", pending: "Criando…" },
  /** Takes something off a list without destroying it — a veto, an exclusion, a term. */
  remove: { label: "Remover", pending: "Removendo…" },
  /** Destroys a record, always behind a preview or a typed confirmation. */
  exclude: { label: "Excluir", pending: "Excluindo…" },
  /** Flips `is_active` to false on a catalogue row. Reversible from the same row. */
  retire: { label: "Aposentar", pending: "Aposentando…" },
  /** Flips `is_active` back to true. Shared with `deactivate`, which is its own action. */
  reactivate: { label: "Reativar", pending: "Reativando…" },
  /** Disables an account. Not a catalogue row: see the note above. */
  deactivate: { label: "Desativar", pending: "Desativando…" },
  /** Launches one worker run. */
  run: { label: "Rodar agora", pending: "Rodando…" },
  /** Unifies two vocabulary entries into one. */
  merge: { label: "Mesclar", pending: "Mesclando…" },
  /** Commits a computed plan — an arrangement proposal, a batch of clusters, a conflict verdict. */
  apply: { label: "Aplicar", pending: "Aplicando…" },
  /**
   * Computes what a destructive write would do, without writing it.
   *
   * Its own entry because it is its own step: every irreversible write in this UI is gated behind a
   * preview, and the screens spelled that gate three ways — `Conferir impacto`, `Conferir o que seria
   * excluído`, `Conferir`. One button, one name.
   */
  preview: { label: "Conferir impacto", pending: "Conferindo…" },
  /** Walks a ledger backwards. */
  undo: { label: "Desfazer", pending: "Desfazendo…" },
  /** Removes a term from an axis without touching the documents. */
  ban: { label: "Banir", pending: "Banindo…" },
  /** Puts a banned term back on its axis. */
  unban: { label: "Desbanir", pending: "Desbanindo…" },
  /** Drops a local draft without writing anything. */
  discard: { label: "Descartar", pending: "Descartando…" },
  /** Abandons a form or a preview. */
  cancel: { label: "Cancelar" },
  /** Closes a panel that is already open. */
  close: { label: "Fechar" },
  /** Re-runs a read-only probe. */
  recheck: { label: "Verificar de novo", pending: "Verificando…" },
} as const satisfies Record<string, Action>;
