import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
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
 */
type NavItem = { to: string; label: string; hint: string; permission?: Permission };

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Curadoria",
    items: [{ to: "/", label: "Início", hint: "O que precisa de mim" }],
  },
  {
    section: "Acervo",
    items: [
      { to: "/acervo/lista", label: "Lista e busca", hint: "Facetas e ranking" },
      { to: "/acervo/arvore", label: "Árvore", hint: "Navegar pelo arranjo" },
      { to: "/acervo/excluidas", label: "Excluídas", hint: "A trilha do que saiu" },
    ],
  },
  {
    section: "Arranjo",
    items: [
      { to: "/arranjo/plano", label: "Plano de arranjo", hint: "Decidir os níveis", permission: "CURATE" },
      { to: "/arranjo/diagnostico", label: "Diagnóstico", hint: "Onde está incoerente" },
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
      { to: "/arranjo/niveis", label: "Níveis de descrição", hint: "A escada NOBRADE", permission: "CATALOGUE" },
      { to: "/arranjo/tipologias", label: "Tipologias", hint: "A forma diplomática", permission: "CATALOGUE" },
      {
        to: "/vocabulario",
        label: "Vocabulário do acervo",
        hint: "Nomes e lugares deste acervo",
        permission: "CATALOGUE",
      },
    ],
  },
  {
    section: "Assuntos",
    items: [
      { to: "/assuntos/tags", label: "Tags", hint: "Peso, duplicatas e merges", permission: "CURATE" },
      {
        to: "/assuntos/categorias",
        label: "Categorias",
        hint: "As gavetas de assunto",
        permission: "CATALOGUE",
      },
      { to: "/assuntos/descobrir", label: "Descobrir gavetas", hint: "Clusters por tema", permission: "CURATE" },
      { to: "/assuntos/excecoes", label: "Não é assunto", hint: "O que a regra não pega", permission: "CURATE" },
    ],
  },
  {
    section: "Entidades",
    items: [
      { to: "/entidades/lista", label: "Entidades", hint: "NER: peso, tipo e merge", permission: "CURATE" },
      { to: "/entidades/excecoes", label: "Exclusões de NER", hint: "Isto é assunto, não nome", permission: "CURATE" },
      { to: "/entidades/conflitos", label: "Conflitos", hint: "Assunto x nome próprio", permission: "CURATE" },
    ],
  },
  {
    section: "Qualidade",
    items: [
      { to: "/qualidade/trechos", label: "Trechos", hint: "Boilerplate e escopo", permission: "CATALOGUE" },
      { to: "/qualidade/regras", label: "Regras", hint: "Reescrever ou sinalizar", permission: "CATALOGUE" },
      { to: "/qualidade/anomalias", label: "Anomalias", hint: "O que o validador marcou", permission: "CURATE" },
    ],
  },
  {
    section: "Sistema",
    items: [
      {
        to: "/sistema/workers",
        label: "Workers de IA",
        hint: "Presets, filas e execução",
        permission: "OPERATE",
      },
      { to: "/sistema/execucoes", label: "Execuções", hint: "O ledger do que rodou", permission: "OPERATE" },
      { to: "/sistema/diagnostico", label: "Diagnóstico", hint: "Banco, modelos e storage", permission: "OPERATE" },
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
    items: [{ to: "/configuracoes/usuarios", label: "Usuários", hint: "Contas, papéis e sessões", permission: "ADMIN" }],
  },
];

export function AppShell() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const [changingPassword, setChangingPassword] = useState(false);

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

  return (
    <div className="flex min-h-full">
      <aside className="flex w-64 shrink-0 flex-col border-r border-(--color-line) bg-(--color-surface)">
        <div className="border-b border-(--color-line) px-4 py-4">
          <p className="text-sm font-semibold">{ATTRIBUTION.name}</p>
          <p className="text-xs text-(--color-muted)">Curadoria do acervo</p>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {NAV.map((group) => {
            // A role sees the screens it can work in, plus every pure read. An empty group is not
            // rendered at all: a heading over nothing is a menu that advertises what it hides.
            const items = group.items.filter((item) => !item.permission || can(user.role, item.permission));
            if (items.length === 0) return null;
            return (
              <div key={group.section} className="mb-3">
                <p className="px-2 pb-1 text-[11px] font-semibold tracking-wide text-(--color-muted) uppercase">
                  {group.section}
                </p>
                <ul>
                  {items.map((item) => {
                    const active = item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
                    return (
                      <li key={item.to}>
                        <Link
                          to={item.to}
                          className={cn(
                            "block rounded-md px-2 py-1.5 text-sm transition",
                            active
                              ? "bg-(--color-accent)/10 font-medium text-(--color-accent)"
                              : "text-(--color-ink) hover:bg-black/[0.04]",
                          )}
                        >
                          {item.label}
                          <span className="block text-[11px] font-normal text-(--color-muted)">{item.hint}</span>
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
 */
function SessionFooter({
  user,
  changing,
  onTogglePassword,
}: {
  user: AuthUser;
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
