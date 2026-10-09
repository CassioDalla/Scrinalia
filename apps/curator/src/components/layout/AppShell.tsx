import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import {
  BookMarked,
  CircleSlash,
  Cpu,
  FileType,
  Flag,
  FolderTree,
  GitCompareArrows,
  HeartPulse,
  History,
  KeyRound,
  Layers,
  LayoutDashboard,
  LogOut,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Ruler,
  Scissors,
  Search,
  Sparkles,
  Tags,
  Trash2,
  TriangleAlert,
  UserCog,
  Users,
  UserX,
  Waypoints,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import { fetchCurrentUser, logout, type AuthUser } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Feedback";
import { ATTRIBUTION } from "@/lib/attribution";
import { cn } from "@/lib/cn";
import { can, ROLE_LABEL, type Permission } from "@/lib/permissions";

import { AttributionFooter } from "./AttributionFooter";
import { LoginForm } from "./LoginForm";
import { PasswordChangeForm } from "./PasswordChangeForm";

/**
 * Navigation mirrors the sitemap.
 *
 * Every entry is a screen that exists and that the API can serve: a menu that offers a route the
 * back-end refuses is worse than one that says "not yet". The public site (``apps/public``) is the
 * only part of the sitemap deliberately absent — it is a separate surface, with its own projection.
 *
 * ``permission`` is the area the screen's **work** needs, and the shell hides the entry when the
 * account does not carry it (cycle B9.2). It is the write permission and not the read one, because
 * reading is what an authenticated session is: the pure reads — the collection, the tree, the
 * diagnostic — carry none and stay reachable by every role, while a screen whose purpose is to
 * decide (curate a record, maintain a catalogue, run a worker, manage accounts) carries the area it
 * writes to. A role that lacks it sees a shorter menu, not a button that answers 403; the 403
 * remains the truth and is what a direct URL still gets.
 *
 * ``icon`` is one glyph per entry, and the set comes from ``lucide-react``. That is the recorded
 * decision of issue #21: a maintained library of consistent 24px glyphs, imported per icon so the
 * bundler keeps only the ones the menu names, instead of twenty-three hand-drawn SVGs inside this
 * file that nothing ever updates. The glyph is the only thing the collapsed rail shows, so it
 * carries the entry's identity on its own — the label stays reachable as its accessible name and as
 * the tooltip.
 */
type NavItem = { to: string; label: string; hint: string; icon: LucideIcon; permission?: Permission };

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Curadoria",
    items: [{ to: "/", label: "Início", hint: "O que precisa de mim", icon: LayoutDashboard }],
  },
  {
    section: "Acervo",
    items: [
      { to: "/acervo/lista", label: "Lista e busca", hint: "Facetas e ranking", icon: Search },
      { to: "/acervo/arvore", label: "Árvore", hint: "Navegar pelo arranjo", icon: Network },
      { to: "/acervo/excluidas", label: "Excluídas", hint: "A trilha do que saiu", icon: Trash2 },
    ],
  },
  {
    section: "Arranjo",
    items: [
      {
        to: "/arranjo/plano",
        label: "Plano de arranjo",
        hint: "Decidir os níveis",
        icon: Waypoints,
        permission: "CURATE",
      },
      { to: "/arranjo/diagnostico", label: "Diagnóstico", hint: "Onde está incoerente", icon: TriangleAlert },
    ],
  },
  {
    /*
      The two closed catalogues the archivist maintains, together and apart from "Arranjo".
      The arrangement is *work* — deciding where each description sits; a catalogue is the
      vocabulary that work is written against. Typologies are not arrangement (and not subject
      either), so filing them under Arranjo would put engine labels in the middle of the tree.
    */
    section: "Catálogos",
    items: [
      {
        to: "/arranjo/niveis",
        label: "Níveis de descrição",
        hint: "A escada NOBRADE",
        icon: Layers,
        permission: "CATALOGUE",
      },
      { to: "/arranjo/tipologias", label: "Tipologias", hint: "A forma diplomática", icon: FileType, permission: "CATALOGUE" },
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
    section: "Assuntos",
    items: [
      { to: "/assuntos/tags", label: "Tags", hint: "Peso, duplicatas e merges", icon: Tags, permission: "CURATE" },
      {
        to: "/assuntos/categorias",
        label: "Categorias",
        hint: "As gavetas de assunto",
        icon: FolderTree,
        permission: "CATALOGUE",
      },
      {
        to: "/assuntos/descobrir",
        label: "Descobrir gavetas",
        hint: "Clusters por tema",
        icon: Sparkles,
        permission: "CURATE",
      },
      {
        to: "/assuntos/excecoes",
        label: "Não é assunto",
        hint: "O que a regra não pega",
        icon: CircleSlash,
        permission: "CURATE",
      },
    ],
  },
  {
    section: "Entidades",
    items: [
      { to: "/entidades/lista", label: "Entidades", hint: "NER: peso, tipo e merge", icon: Users, permission: "CURATE" },
      {
        to: "/entidades/excecoes",
        label: "Exclusões de NER",
        hint: "Isto é assunto, não nome",
        icon: UserX,
        permission: "CURATE",
      },
      {
        to: "/entidades/conflitos",
        label: "Conflitos",
        hint: "Assunto x nome próprio",
        icon: GitCompareArrows,
        permission: "CURATE",
      },
    ],
  },
  {
    section: "Qualidade",
    items: [
      { to: "/qualidade/trechos", label: "Trechos", hint: "Boilerplate e escopo", icon: Scissors, permission: "CATALOGUE" },
      { to: "/qualidade/regras", label: "Regras", hint: "Reescrever ou sinalizar", icon: Ruler, permission: "CATALOGUE" },
      {
        to: "/qualidade/anomalias",
        label: "Anomalias",
        hint: "O que o validador marcou",
        icon: Flag,
        permission: "CURATE",
      },
    ],
  },
  {
    section: "Sistema",
    items: [
      {
        to: "/sistema/workers",
        label: "Workers de IA",
        hint: "Presets, filas e execução",
        icon: Cpu,
        permission: "OPERATE",
      },
      { to: "/sistema/execucoes", label: "Execuções", hint: "O ledger do que rodou", icon: History, permission: "OPERATE" },
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
    /*
      The installation's own settings, at the end and apart from "Sistema".
      
      "Sistema" is what the *machine* is doing (workers, runs, probes) and belongs to whoever
      operates the installation; "Configurações" is what the installation *is* — the accounts first,
      and later the worker settings that today live inside the panel. Both are administrative, and
      neither is curation.
    */
    section: "Configurações",
    items: [
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
    The session, and the whole gate.

    ``retry: false`` is not a detail: the global default retries twice, and retrying a 401 asks the API
    the same question three times to get the same answer — while the archivist watches a spinner
    instead of the sign-in form.
  */
  const session = useQuery({
    queryKey: ["current-user"],
    queryFn: fetchCurrentUser,
    retry: false,
  });

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
    return <LoginForm />;
  }

  const user = session.data;

  // The temporary password the CLI printed. The screens stay out of reach until it is replaced,
  // otherwise the bootstrap's password would become the account's permanent one.
  if (user.must_change_password) {
    return <PasswordChangeForm forced />;
  }

  /*
    Only the groups this account can work in, computed before the render.

    Filtering first is what keeps the separators right when collapsed: the rule is "a line between
    two visible groups", and a group that vanished with the permission filter must not leave one
    behind.
  */
  const groups = NAV.map((group) => ({
    section: group.section,
    items: group.items.filter((item) => !item.permission || can(user.role, item.permission)),
  })).filter((group) => group.items.length > 0);

  const toggleSidebar = () => {
    const next = !collapsed;
    setCollapsed(next);
    writeCollapsed(next);
  };

  return (
    <div className="flex min-h-full">
      <aside
        className={cn(
          "flex shrink-0 flex-col border-r border-(--color-line) bg-(--color-surface) transition-[width] duration-150",
          collapsed ? "w-16" : "w-64",
        )}
      >
        <div className={cn("border-b border-(--color-line)", collapsed ? "px-2 py-2" : "px-4 py-4")}>
          <div className="flex items-center justify-between gap-2">
            {/*
              The brand leaves the rail when it collapses; the attribution itself does not.
              ``AttributionFooter`` renders it at the foot of every screen (ADR 0006), so the rail can
              trade the name for the width without the license term leaving the page.
            */}
            {collapsed ? null : (
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{ATTRIBUTION.name}</p>
                <p className="truncate text-xs text-(--color-muted)">Curadoria do acervo</p>
              </div>
            )}
            <button
              type="button"
              onClick={toggleSidebar}
              aria-expanded={!collapsed}
              aria-controls="app-nav"
              aria-label={collapsed ? "Expandir o menu" : "Recolher o menu"}
              title={collapsed ? "Expandir o menu" : "Recolher o menu"}
              className={cn(
                "grid size-8 shrink-0 place-items-center rounded-md text-(--color-muted) transition hover:bg-black/5 hover:text-(--color-ink)",
                collapsed && "mx-auto",
              )}
            >
              {collapsed ? (
                <PanelLeftOpen className="size-4" aria-hidden />
              ) : (
                <PanelLeftClose className="size-4" aria-hidden />
              )}
            </button>
          </div>
        </div>
        <nav
          id="app-nav"
          aria-label="Menu principal"
          className={cn("flex-1 overflow-y-auto py-3", collapsed ? "px-1.5" : "px-2")}
        >
          {groups.map((group, index) => (
            <div
              key={group.section}
              // Collapsed, a group boundary is a hairline instead of a heading: the words are gone and
              // the separation is still what tells the archivist where one vocabulary ends.
              className={cn(collapsed ? index > 0 && "mt-3 border-t border-(--color-line) pt-3" : "mb-3")}
            >
              {collapsed ? null : (
                <p className="px-2 pb-1 text-[11px] font-semibold tracking-wide text-(--color-muted) uppercase">
                  {group.section}
                </p>
              )}
              <ul className={cn(collapsed && "space-y-1")}>
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
                  return (
                    <li key={item.to}>
                      <Link
                        to={item.to}
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
                          active
                            ? "bg-(--color-accent)/10 font-medium text-(--color-accent)"
                            : "text-(--color-ink) hover:bg-black/[0.04]",
                        )}
                      >
                        <Icon className={cn("shrink-0", collapsed ? "size-5" : "mt-0.5 size-4")} aria-hidden />
                        {collapsed ? (
                          <span className="sr-only">{item.label}</span>
                        ) : (
                          <span className="min-w-0 flex-1">
                            <span className="block">{item.label}</span>
                            <span className="block text-[11px] font-normal text-(--color-muted)">{item.hint}</span>
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <SessionFooter
          user={user}
          collapsed={collapsed}
          changing={changingPassword}
          onTogglePassword={() => setChangingPassword((open) => !open)}
        />
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1">
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
      <div className="flex flex-col items-center gap-2 border-t border-(--color-line) px-1.5 py-3">
        <span
          title={identity}
          aria-label={identity}
          className="grid size-8 place-items-center rounded-full bg-(--color-accent)/10 text-xs font-semibold text-(--color-accent)"
        >
          {user.name.trim().slice(0, 1).toUpperCase() || "?"}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="size-8 px-0"
          title={changing ? "Fechar" : "Trocar senha"}
          aria-label={changing ? "Fechar" : "Trocar senha"}
          onClick={onTogglePassword}
        >
          <KeyRound className="size-4" aria-hidden />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="size-8 px-0"
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
    <div className="border-t border-(--color-line) px-4 py-3">
      <p className="truncate text-sm font-medium">{user.name}</p>
      <p className="truncate text-xs text-(--color-muted)">
        {ROLE_LABEL[user.role]} · {user.email}
      </p>
      <div className="flex items-center gap-1 pt-2">
        <Button variant="ghost" size="sm" onClick={onTogglePassword}>
          {changing ? "Fechar" : "Trocar senha"}
        </Button>
        <Button variant="ghost" size="sm" disabled={signOut.isPending} onClick={() => signOut.mutate()}>
          {signOut.isPending ? "Saindo…" : "Sair"}
        </Button>
      </div>
    </div>
  );
}
