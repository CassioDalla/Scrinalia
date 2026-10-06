import { Link, Outlet, useRouterState } from "@tanstack/react-router";

import { cn } from "@/lib/cn";

/**
 * Navigation mirrors the sitemap.
 *
 * Every entry is a screen that exists and that the API can serve: a menu that offers a route the
 * back-end refuses is worse than one that says "not yet". The public site (``apps/public``) is the
 * only part of the sitemap deliberately absent — it is a separate surface, with its own projection.
 */
type NavItem = { to: string; label: string; hint: string };

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
      { to: "/arranjo/plano", label: "Plano de arranjo", hint: "Decidir os níveis" },
      { to: "/arranjo/diagnostico", label: "Diagnóstico", hint: "Onde está incoerente" },
      { to: "/arranjo/niveis", label: "Catálogo de níveis", hint: "A escada NOBRADE" },
    ],
  },
  {
    section: "Assuntos",
    items: [
      { to: "/assuntos/tags", label: "Tags", hint: "Peso, duplicatas e merges" },
      { to: "/assuntos/categorias", label: "Categorias", hint: "As gavetas de assunto" },
      { to: "/assuntos/descobrir", label: "Descobrir gavetas", hint: "Clusters por tema" },
      { to: "/assuntos/excecoes", label: "Não é assunto", hint: "O que a regra não pega" },
    ],
  },
  {
    section: "Entidades",
    items: [
      { to: "/entidades/lista", label: "Entidades", hint: "NER: peso, tipo e merge" },
      { to: "/entidades/excecoes", label: "Exclusões de NER", hint: "Isto é assunto, não nome" },
      { to: "/entidades/conflitos", label: "Conflitos", hint: "Assunto x nome próprio" },
    ],
  },
  {
    section: "Qualidade",
    items: [
      { to: "/qualidade/trechos", label: "Trechos", hint: "Boilerplate e escopo" },
      { to: "/qualidade/regras", label: "Regras", hint: "Reescrever ou sinalizar" },
      { to: "/qualidade/anomalias", label: "Anomalias", hint: "O que o validador marcou" },
    ],
  },
  {
    section: "Sistema",
    items: [
      { to: "/sistema/workers", label: "Workers de IA", hint: "Presets, filas e execução" },
      { to: "/sistema/execucoes", label: "Execuções", hint: "O ledger do que rodou" },
      { to: "/sistema/diagnostico", label: "Diagnóstico", hint: "Banco, modelos e storage" },
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
