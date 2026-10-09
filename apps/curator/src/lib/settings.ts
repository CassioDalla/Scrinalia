import {
  BookMarked,
  Cpu,
  FileType,
  HeartPulse,
  History,
  Layers,
  UserCog,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

import type { AuthUser } from "@/api/client";
import { can, type Permission } from "@/lib/permissions";

/**
 * What the installation *is*, gathered on `/configuracoes`.
 *
 * These are the screens nobody opens in the middle of cataloguing: the accounts, the closed
 * catalogues, the arrangement plan, the worker panel and the machine probes. They used to sit
 * scattered across the menu — under "Arranjo", "Catálogos", "Sistema" and a "Configurações" section
 * that aggregated a single entry — and the menu paid a quarter of its height for screens the
 * archivist needs once a week. Here they are cards, grouped by the question they answer.
 *
 * The catalogue is **data**, and the two things that read it (this page and the nav entry that leads
 * to it) take the same shape from here, so a card cannot exist on one and not the other: the nav
 * entry follows `SETTINGS_PERMISSIONS`, which is the areas the cards write to, and it is rendered
 * while the account carries at least one of them.
 *
 * Two rules decide what belongs, and both are the shell's own:
 *
 * * **`permission` is the area the screen's *work* needs**, exactly as in the nav — the write
 *   permission, never the read one, because reading is what an authenticated session is. A card is
 *   hidden when the account does not carry it, and the entry disappears when no card survives: the
 *   mirror may hide and must never grant, and the API's 403 remains the truth a direct URL gets.
 * * **A tab is a question, not an audience.** "Arranjo e catálogos" is deliberate: the plan is the
 *   arrangement *work*, and the levels, the typologies and the collection vocabulary are the
 *   vocabularies that work is written against. Calling that tab "Arranjo" would file the catalogues
 *   as arrangement, which they are not — the typology is the diplomatic form of the record, and the
 *   collection vocabulary belongs to neither axis on its own.
 */
export type SettingsCard = {
  /** A screen that exists; the union is closed so a typo here fails the type check. */
  to: SettingsPath;
  label: string;
  hint: string;
  icon: LucideIcon;
  permission: Permission;
};

export type SettingsPath =
  | "/sistema/workers"
  | "/sistema/execucoes"
  | "/sistema/diagnostico"
  | "/arranjo/plano"
  | "/arranjo/niveis"
  | "/arranjo/tipologias"
  | "/vocabulario"
  | "/configuracoes/usuarios";

export type SettingsTab = { id: string; label: string; cards: SettingsCard[] };

/**
 * The tabs, in the order of the permission ladder they walk: the archivist's work first, then the
 * machine, then the installation's own accounts.
 */
export const SETTINGS_TABS: SettingsTab[] = [
  {
    id: "arranjo",
    label: "Arranjo e catálogos",
    cards: [
      {
        to: "/arranjo/plano",
        label: "Plano de arranjo",
        hint: "Decidir os níveis",
        icon: Waypoints,
        permission: "CURATE",
      },
      {
        to: "/arranjo/niveis",
        label: "Níveis de descrição",
        hint: "A escada NOBRADE",
        icon: Layers,
        permission: "CATALOGUE",
      },
      {
        to: "/arranjo/tipologias",
        label: "Tipologias",
        hint: "A forma diplomática",
        icon: FileType,
        permission: "CATALOGUE",
      },
      {
        to: "/vocabulario",
        label: "Vocabulário do acervo",
        hint: "Nomes e lugares deste acervo",
        icon: BookMarked,
        permission: "CATALOGUE",
      },
    ],
  },
  {
    id: "operacao",
    label: "Operação",
    cards: [
      {
        to: "/sistema/workers",
        label: "Workers de IA",
        hint: "Presets, filas e execução",
        icon: Cpu,
        permission: "OPERATE",
      },
      {
        to: "/sistema/execucoes",
        label: "Execuções",
        hint: "O ledger do que rodou",
        icon: History,
        permission: "OPERATE",
      },
      {
        to: "/sistema/diagnostico",
        label: "Diagnóstico",
        hint: "Banco, modelos e storage",
        icon: HeartPulse,
        permission: "OPERATE",
      },
    ],
  },
  {
    id: "acesso",
    label: "Acesso",
    cards: [
      {
        to: "/configuracoes/usuarios",
        label: "Usuários",
        hint: "Contas, papéis e sessões",
        icon: UserCog,
        permission: "ADMIN",
      },
    ],
  },
];

/** The tab ids the URL may carry. Validating against these keeps a hand-written `?aba=` predictable. */
export const SETTINGS_TAB_IDS: string[] = SETTINGS_TABS.map((tab) => tab.id);

/**
 * The areas the cards write to, without repetition.
 *
 * Derived from the catalogue so a card cannot be added without its area reaching the nav entry: this
 * is the "any of" the shell evaluates for `/configuracoes`.
 */
export const SETTINGS_PERMISSIONS: readonly Permission[] = [
  ...new Set(SETTINGS_TABS.flatMap((tab) => tab.cards.map((card) => card.permission))),
];

/**
 * Where the cards lead.
 *
 * The nav entry is the way *back up* to the landing, so it stays marked while the archivist is on
 * one of these screens: they left the menu, and the rail should still say which part of the
 * installation this is instead of showing nothing selected.
 */
export const SETTINGS_PATHS: readonly string[] = SETTINGS_TABS.flatMap((tab) =>
  tab.cards.map((card) => card.to),
);

/**
 * The tabs this account has something in, empty tabs removed.
 *
 * An empty tab is not rendered for the same reason an empty menu group is not: a tab that opens on
 * nothing advertises what it hides.
 */
export function visibleSettingsTabs(role: AuthUser["role"]): SettingsTab[] {
  return SETTINGS_TABS.map((tab) => ({
    ...tab,
    cards: tab.cards.filter((card) => can(role, card.permission)),
  })).filter((tab) => tab.cards.length > 0);
}
