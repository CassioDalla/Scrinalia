import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router";

import { AppShell } from "@/components/layout/AppShell";
import { AnomaliesRoute, validateAnomaliesSearch } from "@/routes/AnomaliesRoute";
import { CategoriesRoute } from "@/routes/CategoriesRoute";
import { CleaningRulesRoute } from "@/routes/CleaningRulesRoute";
import { CollectionRoute, validateCollectionSearch } from "@/routes/CollectionRoute";
import { ConflictsRoute, validateConflictsSearch } from "@/routes/ConflictsRoute";
import { DeletionsRoute, validateDeletionsSearch } from "@/routes/DeletionsRoute";
import { DiagnosticsRoute, validateDiagnosticsSearch } from "@/routes/DiagnosticsRoute";
import { DiscoverRoute } from "@/routes/DiscoverRoute";
import { DocumentRoute } from "@/routes/DocumentRoute";
import { EntitiesRoute, validateEntitiesSearch } from "@/routes/EntitiesRoute";
import { InboxRoute } from "@/routes/InboxRoute";
import { LevelsRoute } from "@/routes/LevelsRoute";
import { NerExclusionsRoute } from "@/routes/NerExclusionsRoute";
import { NotFoundRoute } from "@/routes/NotFoundRoute";
import { PlanRoute, validatePlanSearch } from "@/routes/PlanRoute";
import { SubjectExclusionsRoute } from "@/routes/SubjectExclusionsRoute";
import { TagsRoute, validateTagsSearch } from "@/routes/TagsRoute";
import { TextTemplatesRoute, validateTextTemplatesSearch } from "@/routes/TextTemplatesRoute";
import { TreeRoute, validateTreeSearch } from "@/routes/TreeRoute";

/**
 * Routes are declared in code, not derived from the filesystem.
 *
 * That is a deliberate trade: the file-based router needs a generated route tree, which would make
 * ``tsc`` depend on having run the bundler first — a build-order coupling in CI that buys nothing
 * for a handful of screens.
 */
const rootRoute = createRootRoute({ component: AppShell, notFoundComponent: NotFoundRoute });

const inboxRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: InboxRoute,
});

const collectionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/acervo/lista",
  component: CollectionRoute,
  validateSearch: validateCollectionSearch,
});

/**
 * The tree is a static path and the dossier is a dynamic one under the same parent.
 *
 * TanStack Router ranks a static segment above a parameter, so ``/acervo/arvore`` never resolves as
 * a description id — which is why the tree can live beside ``/acervo/$descriptionId`` without a
 * guard in the dossier.
 */
/**
 * The trail of the deletions. A static path beside ``/acervo/lista`` and ``/acervo/arvore``: it is a
 * ledger of the collection, not a description, and it must never resolve as an id.
 */
const deletionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/acervo/excluidas",
  component: DeletionsRoute,
  validateSearch: validateDeletionsSearch,
});

const treeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/acervo/arvore",
  component: TreeRoute,
  validateSearch: validateTreeSearch,
});

const documentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/acervo/$descriptionId",
  component: DocumentRoute,
  // ``aba`` is optional so a link to the dossier does not have to know which tab it means; the
  // screen falls back to the description tab.
  validateSearch: (search: Record<string, unknown>): { aba?: string } => ({
    aba: typeof search.aba === "string" ? search.aba : undefined,
  }),
});

const planRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/arranjo/plano",
  component: PlanRoute,
  validateSearch: validatePlanSearch,
});

const diagnosticsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/arranjo/diagnostico",
  component: DiagnosticsRoute,
  validateSearch: validateDiagnosticsSearch,
});

const levelsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/arranjo/niveis",
  component: LevelsRoute,
});

const tagsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/assuntos/tags",
  component: TagsRoute,
  validateSearch: validateTagsSearch,
});

const categoriesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/assuntos/categorias",
  component: CategoriesRoute,
});

const discoverRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/assuntos/descobrir",
  component: DiscoverRoute,
});

const subjectExclusionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/assuntos/excecoes",
  component: SubjectExclusionsRoute,
});

const entitiesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/entidades/lista",
  component: EntitiesRoute,
  validateSearch: validateEntitiesSearch,
});

const nerExclusionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/entidades/excecoes",
  component: NerExclusionsRoute,
});

const conflictsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/entidades/conflitos",
  component: ConflictsRoute,
  validateSearch: validateConflictsSearch,
});

const textTemplatesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/qualidade/trechos",
  component: TextTemplatesRoute,
  validateSearch: validateTextTemplatesSearch,
});

const cleaningRulesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/qualidade/regras",
  component: CleaningRulesRoute,
});

const anomaliesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/qualidade/anomalias",
  component: AnomaliesRoute,
  validateSearch: validateAnomaliesSearch,
});

export const router = createRouter({
  routeTree: rootRoute.addChildren([
    inboxRoute,
    collectionRoute,
    deletionsRoute,
    treeRoute,
    documentRoute,
    planRoute,
    diagnosticsRoute,
    levelsRoute,
    tagsRoute,
    categoriesRoute,
    discoverRoute,
    subjectExclusionsRoute,
    entitiesRoute,
    nerExclusionsRoute,
    conflictsRoute,
    textTemplatesRoute,
    cleaningRulesRoute,
    anomaliesRoute,
  ]),
  defaultPreload: "intent",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
