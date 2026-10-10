import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import {
  CircleSlash,
  Flag,
  FolderTree,
  GitCompareArrows,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Network,
  PanelLeftClose,
  Ruler,
  Scissors,
  Search,
  Settings,
  Sparkles,
  Tags,
  Trash2,
  TriangleAlert,
  Users,
  UserX,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { fetchCurrentUser, fetchSetupStatus, logout, type AuthUser } from "@/api/client";
import { Lockup } from "@/components/brand/Lockup";
import { Mark } from "@/components/brand/Mark";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Feedback";
import { cn } from "@/lib/cn";
import { PRODUCT } from "@/lib/copy";
import { can, ROLE_LABEL, type Permission } from "@/lib/permissions";
import { SCREENS, type Screen, type ScreenId } from "@/lib/screens";
import { SETTINGS_PATHS, SETTINGS_PERMISSIONS } from "@/lib/settings";

import { AttributionFooter } from "./AttributionFooter";
import { LoginForm } from "./LoginForm";
import { PasswordChangeForm } from "./PasswordChangeForm";
import { SetupForm } from "./SetupForm";

/**
 * Navigation mirrors the sitemap.
 *
 * Every entry is a screen that exists and that the API can serve: a menu that offers a route the
 * back-end refuses is worse than one that says "not yet". The public site (``apps/public``) is the
 * only part of the sitemap deliberately absent — it is a separate surface, with its own projection.
 *
 * An entry names its **screen** and nothing else: the label and the hint are ``lib/screens.ts``'s,
 * which is also what the settings card and the page's own ``<h1>`` read. That is the fix for the
 * divergence this file used to carry — the menu said ``Tags`` while the page it opened said
 * "Vocabulário de tags", and two different screens were both called "Diagnóstico" — and the coverage
 * gate fails when a route exists without a name or a name without its route.
 *
 * ``permission`` is the area the screen's **work** needs, and the shell hides the entry when the
 * account does not carry it (cycle B9.2). It is the write permission and not the read one, because
 * reading is what an authenticated session is: the pure reads — the collection, the tree, the
 * diagnostic — carry none and stay reachable by every role, while a screen whose purpose is to
 * decide (curate a record, maintain a catalogue, run a worker, manage accounts) carries the area it
 * writes to. A role that lacks it sees a shorter menu, not a button that answers 403; the 403
 * remains the truth and is what a direct URL still gets.
 *
 * ``anyOf`` is the same rule for a page whose work is spread across areas: ``/configuracoes`` is a
 * landing of cards, and it is in the menu while the account can open **at least one** of them. A
 * ``VIEWER`` reaches none, so the entry is not rendered — and the card catalogue
 * (``lib/settings.ts``) is what both this entry and that page read, so the two cannot disagree.
 *
 * Eight entries that used to live here — the arrangement plan, the three catalogue screens, the
 * worker panel, the run ledger, the machine diagnostics and the accounts — are now cards of that
 * landing. They left the menu, not the sitemap: each kept its route and its screen.
 *
 * ``icon`` is one glyph per entry, and the set comes from ``lucide-react``. That is the recorded
 * decision of issue #21: a maintained library of consistent 24px glyphs, imported per icon so the
 * bundler keeps only the ones the menu names, instead of twenty-three hand-drawn SVGs inside this
 * file that nothing ever updates. The glyph is the only thing the collapsed rail shows, so it
 * carries the entry's identity on its own — the label stays reachable as its accessible name and as
 * the tooltip.
 */
type NavItem = {
  /**
   * The screen this entry opens. One id, and the name comes from the catalogue.
   *
   * Neither the label nor the hint is typed here, and that is the fix for the defect this file used
   * to carry: the menu said `Tags` while the page it opened said "Vocabulário de tags", and nothing
   * made the two agree. Now the entry names the screen and `lib/screens.ts` says what it is called —
   * so the rail, the settings card and the page heading read one string, and the coverage gate fails
   * when a route exists without a name.
   */
  screen: ScreenId;
  icon: LucideIcon;
  permission?: Permission;
  anyOf?: readonly Permission[];
  /**
   * Paths that also count as "this entry" for the highlight.
   *
   * The landing's screens left the menu, and without this the rail would show nothing selected while
   * the archivist is standing on one of them.
   */
  alsoActive?: readonly string[];
};

/** ``section`` is optional: the landing at the foot of the menu stands on its own, with no heading. */
type NavGroup = { id: string; section?: string; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    /*
      `Início` stands on its own, with no heading, and the group it used to head is gone.

      "Curadoria" held exactly one entry, which is the same defect the landing at the foot of the
      menu was fixed for — and the comment there already states the rule: *the fix was not a better
      heading*. A section exists to gather, and a section that gathers one line is a line of chrome.
    */
    id: "inicio",
    items: [{ screen: "inbox", icon: LayoutDashboard }],
  },
  {
    id: "acervo",
    section: "Acervo",
    items: [
      { screen: "collection", icon: Search },
      { screen: "tree", icon: Network },
      { screen: "deletions", icon: Trash2 },
      /*
        The arrangement diagnostic sits with the collection and not in a group of its own.

        It reads the tree the three entries above browse — where a code diverges, what is orphaned —
        and it stayed behind when "Arranjo" lost its only other entry (the plan, now a card), so
        keeping the heading would have left a section that exists to hold one line.
       */
      { screen: "diagnostics", icon: TriangleAlert },
    ],
  },
  {
    id: "assuntos",
    section: "Assuntos",
    items: [
      { screen: "tags", icon: Tags, permission: "CURATE" },
      { screen: "categories", icon: FolderTree, permission: "CATALOGUE" },
      { screen: "discover", icon: Sparkles, permission: "CURATE" },
      { screen: "subjectExclusions", icon: CircleSlash, permission: "CURATE" },
    ],
  },
  {
    id: "entidades",
    section: "Entidades",
    items: [
      { screen: "entities", icon: Users, permission: "CURATE" },
      { screen: "nerExclusions", icon: UserX, permission: "CURATE" },
      { screen: "conflicts", icon: GitCompareArrows, permission: "CURATE" },
    ],
  },
  {
    id: "qualidade",
    section: "Qualidade",
    items: [
      { screen: "textTemplates", icon: Scissors, permission: "CATALOGUE" },
      { screen: "cleaningRules", icon: Ruler, permission: "CATALOGUE" },
      { screen: "anomalies", icon: Flag, permission: "CURATE" },
    ],
  },
  {
    /*
      The landing, at the foot of the menu and without a heading.

      "Configurações" used to be a section that aggregated a single entry, and the fix for that was
      not a better heading: everything the installation *is* — the accounts, the catalogues, the
      arrangement plan, the worker panel and the machine probes — became cards of one page, and the
      entry that opens it belongs to no group. It is separated by the hairline the rail already draws
      between groups, and it is in the menu exactly while the account can open a card.
    */
    id: "configuracoes",
    items: [
      {
        screen: "settings",
        icon: Settings,
        anyOf: SETTINGS_PERMISSIONS,
        alsoActive: SETTINGS_PATHS,
      },
    ],
  },
];

/** An entry with the screen's own name resolved. What the render below reads. */
type ResolvedNavItem = NavItem & Screen;

/**
 * Whether the account sees an entry.
 *
 * `permission` is one area and `anyOf` is "at least one of these", which is what a landing of card
 * pages needs: the shell may hide an entry, and it must never be the thing that grants one, so both
 * halves only ever take an entry away.
 */
/**
 * Whether an entry is the one the archivist is standing on.
 *
 * It is a function and not an inline expression because **the group's accordion needs the same
 * answer**: the group of the current screen has to be open, or landing on `/entidades/conflitos`
 * shows `Entidades` collapsed with the active entry hidden inside it.
 */
function isCurrent(item: ResolvedNavItem, pathname: string): boolean {
  if (item.path === "/") return pathname === "/";
  return pathname.startsWith(item.path) || (item.alsoActive ?? []).some((path) => pathname.startsWith(path));
}

function reaches(role: AuthUser["role"], item: NavItem): boolean {
  if (item.permission && !can(role, item.permission)) return false;
  if (item.anyOf && !item.anyOf.some((area) => can(role, area))) return false;
  return true;
}

/**
 * The visible entries, each carrying its screen's path, label and hint.
 *
 * Resolving here — after the permission filter, before the render — is what keeps the separators
 * right when a group empties out, and it is the only place the two catalogues meet: `NAV` decides
 * what the rail offers, `SCREENS` says what each screen is called.
 */
function visibleNav(role: AuthUser["role"]): (Omit<NavGroup, "items"> & { items: ResolvedNavItem[] })[] {
  return NAV.map((group) => ({
    ...group,
    items: group.items
      .filter((item) => reaches(role, item))
      .map((item) => ({ ...item, ...SCREENS[item.screen] })),
  })).filter((group) => group.items.length > 0);
}

/**
 * Whether the rail is collapsed, remembered by the browser.
 *
 * This is presentation state and it stays in the browser: the API owns what the archivist *decides*
 * — a revision, a merge, a verdict — and has no column for how wide a column of the screen is. The
 * key is namespaced because in production the SPA and the API share an origin with whatever else the
 * operator serves from it, and both halves are wrapped because a private window throws on storage
 * rather than answering ``null``: a sidebar that cannot be collapsed is a worse failure than one
 * that cannot remember.
 */
const SIDEBAR_STORAGE_KEY = "scrinalia.curator.sidebar";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "collapsed";
  } catch {
    return false;
  }
}

function writeCollapsed(collapsed: boolean): void {
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "collapsed" : "expanded");
  } catch {
    // A browser that refuses storage still gets the toggle; it just will not remember.
  }
}

export function AppShell() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const [changingPassword, setChangingPassword] = useState(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  /*
    The section the archivist opened by hand, **with the screen it was opened on**.

    The path is part of the state on purpose: it is what expires the choice when they navigate, so
    the menu shows the section of the current screen and never drifts into two by accident. An
    effect that cleared it would do the same job and cost a second render — and React's own lint
    rule says so. It is not persisted, unlike the collapse: it is derived from where they are, so
    there is nothing durable to remember.
  */
  const [opened, setOpened] = useState<{ path: string; group: string } | null>(null);
  const openGroup = opened?.path === pathname ? opened.group : null;

  /*
    The installation, before the session.

    This is the first question the shell asks, and it has to be: while `auth_users` is empty there is
    nobody to sign in, and `/setup/status` is the one thing an anonymous client may read about the
    installation (ADR 0011). It is not retried, for the same reason the session query is not.
  */
  const setup = useQuery({
    queryKey: ["setup-status"],
    queryFn: fetchSetupStatus,
    retry: false,
  });

  /*
    Only a positive `true` counts, so an error can never open the form that creates an administrator.

    If `/setup/status` fails the shell falls back to the sign-in form — the screen it drew before this
    route existed — and a genuinely empty installation whose own API cannot answer it has a bigger
    problem than which form it is showing.
  */
  const needsSetup = setup.data?.needs_setup === true;

  /*
    The session, and the whole gate.

    ``retry: false`` is not a detail: the global default retries twice, and retrying a 401 asks the API
    the same question three times to get the same answer — while the archivist watches a spinner
    instead of the sign-in form.

    It is also not asked while the installation is empty: there is no account it could resolve to, and
    the 401 would be a request whose answer is already known.
  */
  const session = useQuery({
    queryKey: ["current-user"],
    queryFn: fetchCurrentUser,
    retry: false,
    enabled: !needsSetup,
  });

  if (setup.isPending) {
    return (
      <div className="flex min-h-full items-center justify-center">
        <Skeleton className="h-9 w-56" />
      </div>
    );
  }

  // An installation with no account: the screen that creates the first one, and the only time it can
  // ever be reached.
  if (needsSetup) {
    return <PublicShell>
      <SetupForm />
    </PublicShell>;
  }

  if (session.isPending) {
    return (
      <div className="flex min-h-full items-center justify-center">
        <Skeleton className="h-9 w-56" />
      </div>
    );
  }

  // No session, an expired one or a refused one: the same screen, because from here they are the same
  // fact — this browser does not identify anybody.
  if (session.isError || !session.data) {
    return <PublicShell>
      <LoginForm />
    </PublicShell>;
  }

  const user = session.data;

  // The temporary password the CLI printed. The screens stay out of reach until it is replaced,
  // otherwise the bootstrap's password would become the account's permanent one.
  if (user.must_change_password) {
    return <PublicShell>
      <PasswordChangeForm forced />
    </PublicShell>;
  }

  /*
    Only the groups this account can work in, computed before the render.

    Filtering first is what keeps the separators right when collapsed: the rule is "a line between
    two visible groups", and a group that vanished with the permission filter must not leave one
    behind. `visibleNav` also resolves each entry against the screens catalogue here, so the render
    below reads one shape.
  */
  const groups = visibleNav(user.role);

  /*
    The group the archivist is standing in, which is open by construction.

    Without it, landing on `/entidades/conflitos` from a link would show `Entidades` collapsed and
    the active entry — the highlighted one, the whole reason the rail is worth reading — hidden
    inside it.
  */
  const activeGroup = groups.find((group) => group.items.some((item) => isCurrent(item, pathname)))?.id;

  const toggleSidebar = () => {
    const next = !collapsed;
    setCollapsed(next);
    writeCollapsed(next);
  };

  return (
    /*
      The shell is **exactly one viewport tall** and the page never scrolls; what scrolls is the
      content column, inside `main`.

      The version before it used `min-h-full`, so the rail grew to the height of the *page*: on a
      long screen — the entities list, the plan — the whole menu scrolled out of view, and the
      session footer went to the bottom of the document instead of the bottom of the window. The
      `overflow-y-auto` on the nav never engaged, because the nav was never shorter than its
      content. Measured at 1440x900 at the foot of `/entidades/lista`: a blank rail column and no
      menu at all, not just the last entry below the fold.

      `h-dvh` and not `h-screen`: the dynamic viewport unit follows a mobile browser's chrome, so
      the footer does not sit under it. `min-h-0` on the nav and on the content column is what makes
      them scroll instead of growing — a flex child refuses to shrink below its content by default,
      which is the trap that broke this layout in the first place.
    */
    <div className="flex h-dvh overflow-hidden">
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-(--color-rail) bg-(--color-rail) transition-[width] duration-150",
          collapsed ? "w-16" : "w-64",
        )}
      >
        {/*
          The brand block is the identity's dark surface, and the whole rail with it — a dark band
          over a light menu would be two backgrounds meeting for no reason, and would draw a seam
          right under the name.

          The mark is **always on screen**: expanded it is the lockup, collapsed it is the mark
          itself, and there it is also the control that expands the rail — the brand is the thing
          you click to get the words back, which is what makes it worth keeping at 64px.
        */}
        <div className={cn("shrink-0 border-b border-(--color-rail-line)", collapsed ? "px-2 py-3" : "px-4 py-3")}>
          {collapsed ? (
            <button
              type="button"
              onClick={toggleSidebar}
              aria-expanded={false}
              aria-controls="app-nav"
              aria-label="Expandir o menu"
              title="Expandir o menu"
              className="mx-auto grid size-9 place-items-center rounded-md transition hover:bg-(--color-rail-hover)"
            >
              <Mark className="h-7 w-auto text-(--color-rail-ink)" />
            </button>
          ) : (
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <Lockup className="h-8 w-auto text-(--color-rail-ink)" />
                <p className="truncate text-xs text-(--color-rail-muted)">{PRODUCT.tagline}</p>
              </div>
              <button
                type="button"
                onClick={toggleSidebar}
                aria-expanded
                aria-controls="app-nav"
                aria-label="Recolher o menu"
                title="Recolher o menu"
                className="grid size-8 shrink-0 place-items-center rounded-md text-(--color-rail-muted) transition hover:bg-(--color-rail-hover) hover:text-(--color-rail-ink)"
              >
                <PanelLeftClose className="size-4" aria-hidden />
              </button>
            </div>
          )}
        </div>
        <nav
          id="app-nav"
          aria-label="Menu principal"
          className={cn("min-h-0 flex-1 overflow-y-auto py-3", collapsed ? "px-1.5" : "px-2")}
        >
          {groups.map((group, index) => {
            /*
              Collapsed, a group boundary is a hairline instead of a heading and **every** entry is
              shown: the accordion is an affordance of the expanded rail, where the words are, and a
              heading with no label in a 64px column would be a click that says nothing.

              Expanded, a group with no heading — `Início` at the top, `Configurações` at the foot —
              is always open, because there is nothing to click to open it.
            */
            const open = collapsed || !group.section || group.id === activeGroup || group.id === openGroup;
            const panelId = `app-nav-${group.id}`;
            return (
              <div
                key={group.id}
                className={cn(
                  collapsed ? index > 0 && "mt-3 border-t border-(--color-line) pt-3" : "mb-3",
                  !collapsed && !group.section && index > 0 && "mt-3 border-t border-(--color-line) pt-3",
                )}
              >
                {collapsed || !group.section ? null : (
                  <button
                    type="button"
                    onClick={() =>
                      setOpened((current) =>
                        current?.path === pathname && current.group === group.id
                          ? null
                          : { path: pathname, group: group.id },
                      )
                    }
                    aria-expanded={open}
                    aria-controls={panelId}
                    className="flex w-full items-center justify-between rounded-md px-2 pb-1 text-[11px] font-semibold tracking-wide text-(--color-rail-muted) uppercase transition hover:text-(--color-rail-ink)"
                  >
                    {group.section}
                    <span aria-hidden className="text-[9px]">
                      {open ? "▾" : "▸"}
                    </span>
                  </button>
                )}
                <ul id={panelId} className={cn(collapsed && "space-y-1", !open && "hidden")}>
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const active = isCurrent(item, pathname);
                    return (
                    <li key={item.path}>
                      <Link
                        to={item.path}
                        /*
                          The label is the accessible name in both states and the tooltip is the only
                          place the hint survives when the rail is collapsed — a truncated text node
                          would be a label the reader cannot finish.
                        */
                        title={`${item.label} — ${item.hint}`}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                          "rounded-md text-sm transition",
                          collapsed ? "grid place-items-center py-2.5" : "flex items-start gap-2 px-2 py-1.5",
                          /*
                            The accent cannot carry the active entry here: it is `oklch(… 250)` and the
                            rail is `oklch(… 247)`, the same hue, so blue on navy is a highlight nobody
                            can see. The active entry is the surface's own ink on a lighter surface.
                          */
                          active
                            ? "bg-(--color-rail-active) font-medium text-(--color-rail-ink)"
                            : "text-(--color-rail-ink) hover:bg-(--color-rail-hover)",
                        )}
                      >
                        <Icon className={cn("shrink-0", collapsed ? "size-5" : "mt-0.5 size-4")} aria-hidden />
                        {collapsed ? (
                          <span className="sr-only">{item.label}</span>
                        ) : (
                          <span className="min-w-0 flex-1">
                            <span className="block">{item.label}</span>
                            <span className="block text-[11px] font-normal text-(--color-rail-muted)">{item.hint}</span>
                          </span>
                        )}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </nav>

        <SessionFooter
          user={user}
          collapsed={collapsed}
          changing={changingPassword}
          onTogglePassword={() => setChangingPassword((open) => !open)}
        />
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          {changingPassword ? (
            <PasswordChangeForm onDone={() => setChangingPassword(false)} />
          ) : (
            <Outlet />
          )}
        </div>
        <AttributionFooter />
      </main>
    </div>
  );
}

/**
 * The chrome of the screens that come **before** a session: the first-run setup, the sign-in form
 * and the forced password change.
 *
 * They are not inside the rail — there is no session to navigate with — but they are the surface a
 * stranger reaches, and the attribution has to be on it. `AttributionFooter`'s own contract says a
 * notice hidden behind a login is not a notice to the users of a network service, and until now
 * these three returns replaced the whole tree and took the footer with them: the §7(b) elements,
 * and the version, were invisible to anyone without an account.
 *
 * `min-h-dvh` with the form in a `flex-1` box keeps the centring the three forms already had, and
 * puts the footer at the bottom of the window instead of under the fold.
 */
function PublicShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <div className="flex flex-1 flex-col">{children}</div>
      <AttributionFooter />
    </div>
  );
}

/**
 * Who is signed in, and the two things they can do about it.
 *
 * The name and the role are shown because everything this person writes is recorded under them: the
 * ledgers print the name, so a screen that hid it would leave the archivist guessing what their own
 * edits are attributed to.
 *
 * Collapsed, the same three facts move into an initial and two tooltips. The initial is not a
 * decoration: it is the one place the account answers "who am I signed in as" after the name leaves
 * the rail, and it carries the full name, the role and the address in its ``title``.
 */
function SessionFooter({
  user,
  collapsed,
  changing,
  onTogglePassword,
}: {
  user: AuthUser;
  collapsed: boolean;
  changing: boolean;
  onTogglePassword: () => void;
}) {
  const queryClient = useQueryClient();
  const signOut = useMutation({
    mutationFn: logout,
    // Whether the API answered or the session was already over, this browser is signed out: clearing
    // the cached account is what draws the sign-in form.
    onSettled: () => queryClient.setQueryData(["current-user"], null),
  });

  if (collapsed) {
    const identity = `${user.name} · ${ROLE_LABEL[user.role]} · ${user.email}`;
    return (
      <div className="flex shrink-0 flex-col items-center gap-2 border-t border-(--color-rail-line) px-1.5 py-3">
        <span
          title={identity}
          aria-label={identity}
          className="grid size-8 place-items-center rounded-full bg-(--color-rail-active) text-xs font-semibold text-(--color-rail-ink)"
        >
          {user.name.trim().slice(0, 1).toUpperCase() || "?"}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="size-8 px-0 text-(--color-rail-muted) hover:bg-(--color-rail-hover) hover:text-(--color-rail-ink)"
          title={changing ? "Fechar" : "Trocar senha"}
          aria-label={changing ? "Fechar" : "Trocar senha"}
          onClick={onTogglePassword}
        >
          <KeyRound className="size-4" aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="size-8 px-0 text-(--color-rail-muted) hover:bg-(--color-rail-hover) hover:text-(--color-rail-ink)"
          title={signOut.isPending ? "Saindo…" : "Sair"}
          aria-label={signOut.isPending ? "Saindo…" : "Sair"}
          disabled={signOut.isPending}
          onClick={() => signOut.mutate()}
        >
          <LogOut className="size-4" aria-hidden />
        </Button>
      </div>
    );
  }

  return (
    <div className="shrink-0 border-t border-(--color-rail-line) px-4 py-3">
      <p className="truncate text-sm font-medium text-(--color-rail-ink)">{user.name}</p>
      <p className="truncate text-xs text-(--color-rail-muted)">
        {ROLE_LABEL[user.role]} · {user.email}
      </p>
      <div className="flex items-center gap-1 pt-2">
        <Button
          variant="ghost"
          size="sm"
          className="text-(--color-rail-muted) hover:bg-(--color-rail-hover) hover:text-(--color-rail-ink)"
          onClick={onTogglePassword}
        >
          {changing ? "Fechar" : "Trocar senha"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="text-(--color-rail-muted) hover:bg-(--color-rail-hover) hover:text-(--color-rail-ink)"
          disabled={signOut.isPending}
          onClick={() => signOut.mutate()}
        >
          {signOut.isPending ? "Saindo…" : "Sair"}
        </Button>
      </div>
    </div>
  );
}
