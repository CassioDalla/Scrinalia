import { useQuery } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";

import { fetchCurrentUser } from "@/api/client";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState, Skeleton } from "@/components/ui/Feedback";
import { Tabs } from "@/components/ui/Tabs";
import { asEnum } from "@/lib/search";
import { SETTINGS_TAB_IDS, visibleSettingsTabs, type ResolvedSettingsCard } from "@/lib/settings";

const routeApi = getRouteApi("/configuracoes");

export type SettingsSearch = { aba?: string };

export function validateSettingsSearch(search: Record<string, unknown>): SettingsSearch {
  return { aba: asEnum(search.aba, SETTINGS_TAB_IDS) };
}

/**
 * Configurações: the screens that are setup rather than daily work, as cards.
 *
 * The page is a **landing**, not a screen of its own: it writes nothing, and every card leads to a
 * screen that already existed with the same route and the same behaviour — what changed is how the
 * archivist finds it. It reads the session from the shell's cache, so the cards cannot disagree with
 * the menu that got them here.
 *
 * The active tab lives in the URL (`?aba=`), like the dossier's, because a colleague can be sent to
 * "the worker cards" as easily as to a page. A tab the account cannot fill is not rendered, and the
 * URL falls back to the first one it can: a link to a tab that was hidden for the reader still lands
 * somewhere honest.
 */
export function SettingsRoute() {
  const current = useQuery({ queryKey: ["current-user"], queryFn: fetchCurrentUser, retry: false });
  const search = routeApi.useSearch();
  const navigate = useNavigate();

  const tabs = visibleSettingsTabs(current.data?.role ?? "VIEWER");
  // The URL's tab only wins when it survived the permission filter; otherwise the first visible one.
  const active = tabs.find((tab) => tab.id === search.aba) ?? tabs[0];
  const cards = active?.cards ?? [];

  return (
    <>
      {/*
        The subtitle comes from the screens catalogue, and it stays a sentence rather than the list of
        areas: the page shows each account only the cards its role carries, so naming "contas,
        catálogos, arranjo e operação" would enumerate what a curator cannot have and would still
        announce accounts on the empty page a viewer lands on.
      */}
      <PageHeader screen="settings" />

      {current.isPending ? (
        <div className="grid gap-3 px-6 py-5 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-28" />
          ))}
        </div>
      ) : tabs.length === 0 ? (
        /*
          A direct URL, not a broken screen. The menu hides this entry for an account that carries
          none of the areas below, and the page says the same thing the missing entry says.
        */
        <div className="px-6 py-5">
          <EmptyState
            title="Nada para configurar"
            hint="Os cartões desta página são as telas de configuração da instalação — contas, catálogos, arranjo e operação —, e o seu papel não carrega nenhuma delas. Foi por isso que a entrada não apareceu no menu."
          />
        </div>
      ) : (
        <>
          {/*
            One visible tab is not a choice: a bar with a single tab is the same noise as a menu
            heading over one entry, so it is not rendered.
          */}
          {tabs.length > 1 ? (
            <div className="px-6">
              <Tabs
                items={tabs.map(({ id, label }) => ({ id, label }))}
                active={active?.id ?? ""}
                onChange={(id) => navigate({ to: "/configuracoes", search: { aba: id } })}
              />
            </div>
          ) : null}

          <div className="grid gap-3 px-6 py-5 sm:grid-cols-2 xl:grid-cols-3">
            {cards.map((card) => (
              <SettingsCardLink key={card.path} card={card} />
            ))}
          </div>
        </>
      )}
    </>
  );
}

/**
 * One card: the screen's name, what it decides, and the way in.
 *
 * The same shape as the work list's cards on purpose — the archivist already reads "nome, uma frase,
 * abrir" everywhere else — with the icon the entry used to carry in the menu.
 */
function SettingsCardLink({ card }: { card: ResolvedSettingsCard }) {
  const Icon = card.icon;
  return (
    <Link to={card.path} className="transition hover:ring-(--color-accent)/40">
      <Card className="h-full hover:ring-(--color-accent)/40">
        <CardBody className="flex h-full flex-col gap-2">
          <div className="flex items-center gap-2">
            <Icon className="size-4 shrink-0 text-(--color-muted)" aria-hidden />
            <span className="text-sm font-medium">{card.label}</span>
          </div>
          <p className="text-xs text-(--color-muted)">{card.hint}</p>
          <div className="mt-auto pt-1">
            <span className="text-xs font-medium text-(--color-accent)">abrir →</span>
          </div>
        </CardBody>
      </Card>
    </Link>
  );
}
