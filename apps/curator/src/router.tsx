import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router";

import { AppShell } from "@/components/layout/AppShell";
import { CategoriesRoute } from "@/routes/CategoriesRoute";
import { CollectionRoute, validateCollectionSearch } from "@/routes/CollectionRoute";
import { DiagnosticsRoute, validateDiagnosticsSearch } from "@/routes/DiagnosticsRoute";
import { DocumentRoute } from "@/routes/DocumentRoute";
import { InboxRoute } from "@/routes/InboxRoute";
import { NotFoundRoute } from "@/routes/NotFoundRoute";
import { PlanRoute, validatePlanSearch } from "@/routes/PlanRoute";
import { TagsRoute, validateTagsSearch } from "@/routes/TagsRoute";

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

export const router = createRouter({
  routeTree: rootRoute.addChildren([
    inboxRoute,
    collectionRoute,
    documentRoute,
    planRoute,
    diagnosticsRoute,
    tagsRoute,
    categoriesRoute,
  ]),
  defaultPreload: "intent",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
