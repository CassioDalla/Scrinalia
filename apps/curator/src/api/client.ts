import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

/**
 * The only client in the application.
 *
 * Requests go through ``openapi-fetch`` over the schema generated from the API's OpenAPI document,
 * so a route or a field that changes on the back-end becomes a **type error here** instead of a
 * runtime surprise. A hand-written ``fetch`` would be invisible to that check, which is why ESLint
 * forbids the global in this workspace.
 *
 * ``baseUrl`` is empty on purpose: in development Vite proxies ``/api`` to the API, and in
 * production Litestar serves this build from the same origin — so there is no CORS anywhere and no
 * environment variable to get wrong.
 */
export const client = createClient<paths>({ baseUrl: "" });

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ApiResult = { data?: unknown; error?: unknown; response: Response };

/**
 * Unwraps an openapi-fetch result into the value, or throws {@link ApiError}.
 *
 * TanStack Query treats a rejection as a failed query and a resolved value as data, so the error
 * shape is decided once, here, instead of in every screen. The generic is on the *caller*: the
 * client's success type is already precise, so ``unwrap<T>`` only re-states what the route returns.
 */
async function unwrap<T>(result: ApiResult): Promise<T> {
  if (result.error !== undefined) {
    const payload = result.error as { error_code?: string; message?: string; detail?: string } | null;
    throw new ApiError(
      result.response.status,
      payload?.error_code ?? "UNKNOWN",
      payload?.message ?? payload?.detail ?? `Erro ${result.response.status}`,
    );
  }
  return result.data as T;
}

// --- Types the screens use, taken from the contract itself -------------------------------------

export type DocumentSummary = components["schemas"]["DocumentSummary"];
export type DocumentListResponse = components["schemas"]["DocumentListResponse"];
export type DocumentFacets = components["schemas"]["DocumentFacets"];
export type DocumentTagSummary = components["schemas"]["DocumentTagSummary"];
export type DocumentEntitySummary = components["schemas"]["DocumentEntitySummary"];
export type FacetCount = components["schemas"]["FacetCount"];
export type CurationInbox = components["schemas"]["CurationInbox"];
export type CurationQueue = components["schemas"]["CurationQueue"];
export type DocumentRevision = components["schemas"]["DocumentRevisionDTO"];
export type DescriptionLevel = components["schemas"]["DescriptionLevelDTO"];
export type ArchiveReviewStatus = components["schemas"]["ArchiveReviewStatus"];
export type DocumentUpdateRequest = components["schemas"]["DocumentUpdateRequest"];

// --- The arrangement (Fase 2.5): the plan catalogue, the ledger and the diagnosis --------------
export type HierarchyNodePlan = components["schemas"]["HierarchyNodePlanDTO"];
export type HierarchyPlanList = components["schemas"]["HierarchyPlanListResponse"];
export type HierarchyPlanSuggestion = components["schemas"]["HierarchyPlanSuggestionResponse"];
export type HierarchyVocabulary = components["schemas"]["HierarchyVocabulary"];
export type PlanDecision = components["schemas"]["HierarchyPlanDecisionRequest"];
export type MaterialisationRequest = components["schemas"]["HierarchyMaterialisationRequest"];
export type MaterialisationPreview = components["schemas"]["HierarchyMaterialisationPreview"];
export type MaterialisationResult = components["schemas"]["HierarchyMaterialisationResult"];
export type MaterialisationItem = components["schemas"]["HierarchyMaterialisationItem"];
export type MaterialisationLog = components["schemas"]["HierarchyMaterialisationLogListResponse"];
export type MaterialisationLogEntry = components["schemas"]["HierarchyMaterialisationLogDTO"];
export type Diagnostic = components["schemas"]["HierarchyDiagnostic"];
export type DiagnosticList = components["schemas"]["HierarchyDiagnosticListResponse"];
export type DiagnosticSummary = components["schemas"]["HierarchyDiagnosticSummary"];

/**
 * The status of a rung, taken from the request the API accepts rather than written here.
 *
 * A literal union would be a second copy of the vocabulary: the contract already enumerates the
 * three values, and a fourth added on the back-end has to reach this screen.
 */
export type PlanStatus = PlanDecision["status"];

// --- The vocabulary of the dossier: tags, entities and the drawers of subject ------------------
export type TagSearchResult = components["schemas"]["TagSearchResult"];
export type TagCurationRequest = components["schemas"]["TagCurationRequest"];
export type TagCurationResult = components["schemas"]["TagCurationResult"];
export type EntityRelevance = components["schemas"]["EntityRelevance"];
export type MacroCategory = components["schemas"]["ArchiveMacroCategoryEntityDTO"];
export type HierarchyNodeMoveRequest = components["schemas"]["HierarchyNodeMoveRequest"];
export type HierarchyNodeSummary = components["schemas"]["HierarchyNodeSummary"];

/**
 * The issue codes the diagnostics route accepts, exactly as the contract declares them.
 *
 * The route's query parameter is an enum, and the codes the screen iterates over arrive from
 * ``GET /hierarchy/flags`` — which is the same vocabulary, delivered as data. One cast at this
 * boundary is the price of reading a list the API owns instead of embedding a second copy here.
 */
export type DiagnosticIssue = NonNullable<
  paths["/api/v1/hierarchy/diagnostics"]["get"]["parameters"]["query"]
>["issue"];

export type SearchMode = "lexical" | "semantic";

/** Every filter the collection search accepts; they all live in the URL. */
export type DocumentSearch = {
  term?: string;
  mode?: SearchMode;
  typology_id?: number;
  macro_category_id?: number;
  level_id?: number;
  ancestor_id?: string;
  entity_type?: string;
  date_from?: string;
  date_to?: string;
  status?: ArchiveReviewStatus;
  limit?: number;
  offset?: number;
};

export async function fetchInbox(): Promise<CurationInbox> {
  return unwrap<CurationInbox>(await client.GET("/api/v1/curation/inbox"));
}

export async function fetchDocuments(search: DocumentSearch): Promise<DocumentListResponse> {
  return unwrap<DocumentListResponse>(
    await client.GET("/api/v1/documents", {
      params: { query: search },
    }),
  );
}

export async function fetchDocument(descriptionId: string): Promise<DocumentSummary> {
  return unwrap<DocumentSummary>(
    await client.GET("/api/v1/documents/{description_id}", {
      params: { path: { description_id: descriptionId } },
    }),
  );
}

export async function fetchRevisions(descriptionId: string): Promise<DocumentRevision[]> {
  return unwrap<DocumentRevision[]>(
    await client.GET("/api/v1/documents/{description_id}/revisions", {
      params: { path: { description_id: descriptionId } },
    }),
  );
}

export async function updateDocument(
  descriptionId: string,
  body: DocumentUpdateRequest,
): Promise<DocumentSummary> {
  return unwrap<DocumentSummary>(
    await client.PATCH("/api/v1/documents/{description_id}", {
      params: { path: { description_id: descriptionId } },
      body,
    }),
  );
}

export async function fetchLevels(): Promise<DescriptionLevel[]> {
  return unwrap<DescriptionLevel[]>(
    await client.GET("/api/v1/hierarchy/levels", { params: { query: { only_active: true } } }),
  );
}

export async function linkTag(
  descriptionId: string,
  tagId: number,
  changedBy?: string,
): Promise<DocumentSummary> {
  return unwrap<DocumentSummary>(
    await client.POST("/api/v1/documents/{description_id}/tags", {
      params: { path: { description_id: descriptionId } },
      body: { tag_id: tagId, changed_by: changedBy ?? null, review_note: null },
    }),
  );
}

export async function unlinkTag(
  descriptionId: string,
  tagId: number,
  changedBy?: string,
): Promise<DocumentSummary> {
  return unwrap<DocumentSummary>(
    await client.DELETE("/api/v1/documents/{description_id}/tags/{tag_id}", {
      params: {
        path: { description_id: descriptionId, tag_id: tagId },
        query: { changed_by: changedBy ?? null, review_note: null },
      },
    }),
  );
}

export async function unlinkEntity(
  descriptionId: string,
  entityId: number,
  changedBy?: string,
): Promise<DocumentSummary> {
  return unwrap<DocumentSummary>(
    await client.DELETE("/api/v1/documents/{description_id}/entities/{entity_id}", {
      params: {
        path: { description_id: descriptionId, entity_id: entityId },
        query: { changed_by: changedBy ?? null, review_note: null },
      },
    }),
  );
}

export async function linkEntity(
  descriptionId: string,
  entityId: number,
  changedBy?: string,
): Promise<DocumentSummary> {
  return unwrap<DocumentSummary>(
    await client.POST("/api/v1/documents/{description_id}/entities", {
      params: { path: { description_id: descriptionId } },
      body: { entity_id: entityId, changed_by: changedBy ?? null, review_note: null },
    }),
  );
}

/**
 * Reparents and/or re-levels a description.
 *
 * ``new_parent_id`` is explicit even when unchanged, and ``null`` means "to the root" — the route
 * states where the node goes. That is why the arrangement tab always sends the parent it shows
 * instead of sending only the field the archivist touched.
 */
export async function moveHierarchyNode(
  descriptionId: string,
  body: HierarchyNodeMoveRequest,
): Promise<HierarchyNodeSummary> {
  return unwrap<HierarchyNodeSummary>(
    await client.POST("/api/v1/hierarchy/nodes/{description_id}/move", {
      params: { path: { description_id: descriptionId } },
      body,
    }),
  );
}

// --- The vocabulary: finding a tag or an entity by name ----------------------------------------

/**
 * Tags matching what the archivist is typing.
 *
 * The route answers an empty list below two characters, so the box never asks for a slice of the
 * whole catalogue. Replaces an input that asked for the **id** of a tag, which no archivist knows.
 */
export async function searchTags(term: string, limit = 10): Promise<TagSearchResult[]> {
  return unwrap<TagSearchResult[]>(
    await client.GET("/api/v1/taxonomy/tags", { params: { query: { term, limit } } }),
  );
}

/** Entities matching what the archivist is typing, most used first. */
export async function searchEntities(term: string, limit = 10): Promise<EntityRelevance[]> {
  return unwrap<EntityRelevance[]>(
    await client.GET("/api/v1/taxonomy/entities", { params: { query: { term, limit } } }),
  );
}

/**
 * Moves one tag into a subject drawer, or declares it is not a subject.
 *
 * A global decision about the vocabulary: it changes the badge of every description carrying the
 * tag, which the screen has to say out loud.
 */
export async function curateTag(tagId: number, body: TagCurationRequest): Promise<TagCurationResult> {
  return unwrap<TagCurationResult>(
    await client.PATCH("/api/v1/taxonomy/tags/{tag_id}", {
      params: { path: { tag_id: tagId } },
      body,
    }),
  );
}

export async function fetchMacroCategories(onlyActive = false): Promise<MacroCategory[]> {
  return unwrap<MacroCategory[]>(
    await client.GET("/api/v1/taxonomy/macro-categories", { params: { query: { only_active: onlyActive } } }),
  );
}

// --- Arrangement: decisions about the tree -----------------------------------------------------

/**
 * The vocabularies the arrangement screens group by.
 *
 * Read from the API instead of being embedded here: ``NEAR_DUPLICATE_NODE`` is a statement about
 * codes the tree does not contain yet, and a hardcoded list would happily offer it as a
 * diagnostic the endpoint refuses.
 */
export async function fetchHierarchyVocabulary(): Promise<HierarchyVocabulary> {
  return unwrap<HierarchyVocabulary>(await client.GET("/api/v1/hierarchy/flags"));
}

export async function fetchHierarchyPlans(params: {
  status?: PlanStatus;
  limit?: number;
  offset?: number;
}): Promise<HierarchyPlanList> {
  return unwrap<HierarchyPlanList>(
    await client.GET("/api/v1/hierarchy/plans", { params: { query: params } }),
  );
}

/** Idempotent, and it never overwrites a decision: the same rungs are not asked again. */
export async function suggestHierarchyPlans(): Promise<HierarchyPlanSuggestion> {
  return unwrap<HierarchyPlanSuggestion>(await client.POST("/api/v1/hierarchy/plans/suggest"));
}

export async function decideHierarchyPlan(planId: number, body: PlanDecision): Promise<HierarchyNodePlan> {
  return unwrap<HierarchyNodePlan>(
    await client.PATCH("/api/v1/hierarchy/plans/{plan_id}", {
      params: { path: { plan_id: planId } },
      body,
    }),
  );
}

/**
 * The dry run, and the only road to the apply.
 *
 * It is computed by the same planner the write executes, so the numbers the archivist reads here
 * are the ones the write produces — which is why the screen never offers the apply before a preview.
 */
export async function previewMaterialisation(body: MaterialisationRequest): Promise<MaterialisationPreview> {
  return unwrap<MaterialisationPreview>(
    await client.POST("/api/v1/hierarchy/materialisation/preview", { body }),
  );
}

export async function applyMaterialisation(body: MaterialisationRequest): Promise<MaterialisationResult> {
  return unwrap<MaterialisationResult>(
    await client.POST("/api/v1/hierarchy/materialisation/apply", { body }),
  );
}

export async function fetchMaterialisationLog(params: {
  include_undone?: boolean;
  limit?: number;
  offset?: number;
}): Promise<MaterialisationLog> {
  return unwrap<MaterialisationLog>(
    await client.GET("/api/v1/hierarchy/materialisation/log", { params: { query: params } }),
  );
}

/** Reverses one run from the ledger. The ledger entry survives, with ``undone_at`` set. */
export async function undoMaterialisation(materialisationId: number, undoneBy?: string): Promise<void> {
  await unwrap<unknown>(
    await client.DELETE("/api/v1/hierarchy/materialisation/log/{materialisation_id}", {
      params: {
        path: { materialisation_id: materialisationId },
        query: { undone_by: undoneBy ?? null },
      },
    }),
  );
}

// --- Arrangement: the structural diagnosis -----------------------------------------------------

export async function fetchDiagnosticSummary(): Promise<DiagnosticSummary> {
  return unwrap<DiagnosticSummary>(await client.GET("/api/v1/hierarchy/diagnostics/summary"));
}

export async function fetchDiagnostics(
  issue: string,
  params: { limit?: number; offset?: number },
): Promise<DiagnosticList> {
  return unwrap<DiagnosticList>(
    await client.GET("/api/v1/hierarchy/diagnostics", {
      params: { query: { issue: issue as DiagnosticIssue, ...params } },
    }),
  );
}
