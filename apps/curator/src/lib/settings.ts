import {
  BookMarked,
  Cpu,
  FileType,
  HeartPulse,
  History,
  Layers,
  SlidersHorizontal,
  UserCog,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

import type { AuthUser } from "@/api/client";
import { can, type Permission } from "@/lib/permissions";
import { SCREENS, type Screen, type ScreenId } from "@/lib/screens";

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
 * A card names its **screen**, and neither its label nor its hint is typed here. That is the same
 * rule the menu follows, and it is what removed the divergences this file carried: the card said
 * "Diagnóstico" for the machine probes while the menu used the same word for the arrangement ones,
 * and it said "Níveis de descrição" while the page's own heading said "Catálogo de níveis". The card,
 * the rail and the heading now read one record from `lib/screens.ts`.
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
  screen: SettingsScreenId;
  icon: LucideIcon;
  permission: Permission;
};

/**
 * The screens reachable from the landing.
 *
 * A subset of `ScreenId` and not a bare string: every screen the landing offers is one of them — the
 * eight that left the menu, plus the worker configuration the split of issue #53 added — and
 * narrowing the type means a card cannot be added for a screen that has no name, or for one that is
 * already an entry in the rail.
 */
export type SettingsScreenId = Extract<
  ScreenId,
  | "plan"
  | "levels"
  | "typologies"
  | "vocabulary"
  | "workers"
  | "workerSettings"
  | "runs"
  | "health"
  | "users"
>;

/** A card with its screen's name resolved. What the page renders. */
export type ResolvedSettingsCard = SettingsCard & Screen;

export type SettingsTab = { id: string; label: string; cards: SettingsCard[] };
export type ResolvedSettingsTab = { id: string; label: string; cards: ResolvedSettingsCard[] };

/**
 * The tabs, in the order of the permission ladder they walk: the archivist's work first, then the
 * machine, then the installation's own accounts.
 */
export const SETTINGS_TABS: SettingsTab[] = [
  {
    id: "arranjo",
    label: "Arranjo e catálogos",
    cards: [
      { screen: "plan", icon: Waypoints, permission: "CURATE" },
      { screen: "levels", icon: Layers, permission: "CATALOGUE" },
      { screen: "typologies", icon: FileType, permission: "CATALOGUE" },
      { screen: "vocabulary", icon: BookMarked, permission: "CATALOGUE" },
    ],
  },
  {
    id: "operacao",
    label: "Operação",
    cards: [
      { screen: "workers", icon: Cpu, permission: "OPERATE" },
      /*
        The configuration sits beside the panel it configures, and the two are separate cards
        because they answer different questions: the panel says what the machine is *doing* (queues,
        pending counters, a run in flight), and this one says what the installation is *set* to do
        (the persisted default and its history). Both declare `OPERATE` — the split moved where the
        write is made, not who may make it.
      */
      { screen: "workerSettings", icon: SlidersHorizontal, permission: "OPERATE" },
      { screen: "runs", icon: History, permission: "OPERATE" },
      { screen: "health", icon: HeartPulse, permission: "OPERATE" },
    ],
  },
  {
    id: "acesso",
    label: "Acesso",
    cards: [{ screen: "users", icon: UserCog, permission: "ADMIN" }],
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
 * installation this is instead of showing nothing selected. Taken from the screens catalogue, so a
 * path here cannot drift from the route it names.
 */
export const SETTINGS_PATHS: readonly string[] = SETTINGS_TABS.flatMap((tab) =>
  tab.cards.map((card) => SCREENS[card.screen].path),
);

/**
 * The tabs this account has something in, empty tabs removed.
 *
 * An empty tab is not rendered for the same reason an empty menu group is not: a tab that opens on
 * nothing advertises what it hides. Each surviving card is resolved against the screens catalogue
 * here, so the page reads `card.label`, `card.hint` and `card.path` the way it always read its own
 * fields.
 */
export function visibleSettingsTabs(role: AuthUser["role"]): ResolvedSettingsTab[] {
  return SETTINGS_TABS.map((tab) => ({
    ...tab,
    cards: tab.cards
      .filter((card) => can(role, card.permission))
      .map((card) => ({ ...card, ...SCREENS[card.screen] })),
  })).filter((tab) => tab.cards.length > 0);
}
