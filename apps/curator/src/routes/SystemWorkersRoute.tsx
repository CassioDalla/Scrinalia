import { getRouteApi, useNavigate } from "@tanstack/react-router";

import { PageBody } from "@/components/layout/PageBody";
import { PageHeader } from "@/components/layout/PageHeader";
import { Tabs } from "@/components/ui/Tabs";
import { RunsLedger, validateSystemRunsSearch, type SystemRunsSearch } from "@/components/workers/RunsLedger";
import { WorkersPanel } from "@/components/workers/WorkersPanel";
import { asEnum } from "@/lib/search";
import { useCopy } from "@/i18n/context";

const routeApi = getRouteApi("/sistema/workers");

/** The two questions the screen answers, and the tab each one is. */
export type WorkersTab = "painel" | "execucoes";

const TAB_IDS: readonly WorkersTab[] = ["painel", "execucoes"];

/**
 * The merged search: the tab, plus the ledger's filters.
 *
 * The filters belong to the route and not to the tab component, because the URL is the state and a
 * deep link (`?aba=execucoes&worker=ner&run=42`) has to survive a reload and a share. The tab is
 * validated against `TABS`, so a hand-written `?aba=` lands on the panel instead of an empty body;
 * the ledger's half is `validateSystemRunsSearch`, the one definition of what that list accepts.
 */
export type SystemWorkersSearch = SystemRunsSearch & { aba?: WorkersTab };

export function validateSystemWorkersSearch(search: Record<string, unknown>): SystemWorkersSearch {
  return {
    ...validateSystemRunsSearch(search),
    aba: asEnum(search.aba, TAB_IDS),
  };
}

/**
 * The operations screen: what the machine is doing, and what it did.
 *
 * One route with two tabs in the URL since #207, reached from the Configurações landing. The panel
 * enqueues and the ledger answers what happened; keeping them a tab apart is the point — the
 * operator used to enqueue on one screen and leave for another to see the result. The configuration
 * stays a screen of its own (`/configuracoes/workers`, #53): it answers a different question, and
 * this issue changed the door, not the meaning. The old ledger path redirects here, filters and all.
 *
 * Only the active tab is mounted, so only its queries run: the panel polls at 5 s while a run is in
 * flight and 15 s while one is queued, and the ledger at 5 s while an entry is active. Mounting both
 * would double the reads for a screen nobody is looking at.
 */
export function SystemWorkersRoute() {
  const messages = useCopy();
  const TABS = TAB_IDS.map((id) => ({ id, label: messages.pages.workers[id] }));
  const search = routeApi.useSearch();
  const navigate = useNavigate();

  /**
   * The URL is the state, and a filter change returns to the first page.
   *
   * `run` is dropped by anything that is not itself: it highlights the row the panel's link pointed
   * at, and after a filter change that row may not even be in the list — a ring around nothing reads
   * as a filter that is not there. Pagination drops it for the same reason.
   */
  const patch = (changes: Partial<SystemWorkersSearch>) =>
    navigate({
      to: "/sistema/workers",
      search: {
        ...search,
        ...changes,
        run: "run" in changes ? changes.run : undefined,
        offset: changes.offset,
      },
    });

  return (
    <>
      <PageHeader screen="workers" />
      <div className="px-6">
        <Tabs items={TABS} active={search.aba ?? "painel"} onChange={(id) => patch({ aba: id as WorkersTab })} />
      </div>
      <PageBody>
        {search.aba === "execucoes" ? <RunsLedger search={search} patch={patch} /> : <WorkersPanel />}
      </PageBody>
    </>
  );
}
