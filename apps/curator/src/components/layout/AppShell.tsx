import { Link, Outlet, useRouterState } from "@tanstack/react-router";

import { cn } from "@/lib/cn";

/**
 * Navigation mirrors the sitemap, and only the screens that exist are enabled.
 *
 * The disabled entries are deliberate and are not hidden: the archivist has to be able to see the
 * shape of the tool, and a menu that grows silently is harder to learn than one that says "not
 * yet". Each of them corresponds to a wave of the plan.
 */
type NavItem = { to: string; label: string; hint: string; enabled: boolean };

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Curadoria",
    items: [{ to: "/", label: "Início", hint: "O que precisa de mim", enabled: true }],
  },
  {
    section: "Acervo",
    items: [
      { to: "/acervo/lista", label: "Lista e busca", hint: "Facetas e ranking", enabled: true },
      { to: "/acervo/arvore", label: "Árvore", hint: "Arranjo materializado", enabled: false },
    ],
  },
  {
    section: "Arranjo",
    items: [
      { to: "/arranjo/plano", label: "Plano de arranjo", hint: "Decidir os níveis", enabled: false },
      { to: "/arranjo/diagnostico", label: "Diagnóstico", hint: "Onde está incoerente", enabled: false },
    ],
  },
  {
    section: "Assuntos",
    items: [
      { to: "/assuntos/tags", label: "Tags", hint: "Merge, undo, stopwords", enabled: false },
      { to: "/assuntos/categorias", label: "Categorias", hint: "As gavetas de assunto", enabled: false },
    ],
  },
  {
    section: "Entidades",
    items: [{ to: "/entidades/lista", label: "Entidades", hint: "NER: merge e tipos", enabled: false }],
  },
  {
    section: "Qualidade",
    items: [
      { to: "/qualidade/trechos", label: "Trechos", hint: "Boilerplate e escopo", enabled: false },
      { to: "/qualidade/anomalias", label: "Anomalias", hint: "O que o validador marcou", enabled: false },
    ],
  },
];

export function AppShell() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });

  return (
    <div className="flex min-h-full">
      <aside className="flex w-64 shrink-0 flex-col border-r border-(--color-line) bg-(--color-surface)">
        <div className="border-b border-(--color-line) px-4 py-4">
          <p className="text-sm font-semibold">Memória Curitibana</p>
          <p className="text-xs text-(--color-muted)">Curadoria do acervo</p>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {NAV.map((group) => (
            <div key={group.section} className="mb-3">
              <p className="px-2 pb-1 text-[11px] font-semibold tracking-wide text-(--color-muted) uppercase">
                {group.section}
              </p>
              <ul>
                {group.items.map((item) => {
                  const active = item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
                  if (!item.enabled) {
                    return (
                      <li key={item.to}>
                        <span
                          title="Ainda não implementado"
                          className="flex cursor-not-allowed items-center justify-between rounded-md px-2 py-1.5 text-sm text-(--color-muted)/60"
                        >
                          {item.label}
                          <span className="text-[10px] tracking-wide uppercase">—</span>
                        </span>
                      </li>
                    );
                  }
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
          ))}
        </nav>
      </aside>

      <main className="min-w-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
