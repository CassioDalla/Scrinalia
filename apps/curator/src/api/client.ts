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
export type MacroCategoryCreateRequest = components["schemas"]["MacroCategoryCreateRequest"];
export type MacroCategoryUpdateRequest = components["schemas"]["MacroCategoryUpdateRequest"];
export type TagRelevanceResponse = components["schemas"]["TagRelevanceResponse"];
export type TagRelevanceCount = components["schemas"]["TagRelevanceCount"];
export type TagRelevanceIdf = components["schemas"]["TagRelevanceIdf"];
export type TagSimilarity = components["schemas"]["TagSimilarity"];
export type TagPairSimilarity = components["schemas"]["TagPairSimilarity"];
export type TagMergeProposal = components["schemas"]["TagMergeProposalDTO"];
export type TagMergeProposalList = components["schemas"]["TagMergeProposalListResponse"];
export type MergeProposalDecision = components["schemas"]["MergeProposalDecisionRequest"];
export type MergeSuggestionRun = components["schemas"]["MergeSuggestionRunResponse"];
export type MergePreview = components["schemas"]["MergePreviewResponse"];
export type BatchMergeResponse = components["schemas"]["BatchMergeResponse"];
export type MergeLogList = components["schemas"]["MergeLogListResponse"];
export type MergeLogEntry = components["schemas"]["MergeLogEntryDTO"];
export type MergeResponse = components["schemas"]["MergeResponse"];
export type Stopword = components["schemas"]["StopwordDTO"];
export type StopwordPurgePreview = components["schemas"]["StopwordPurgePreview"];
export type StopwordPurgeTag = components["schemas"]["StopwordPurgeTag"];
export type StopwordBanResponse = components["schemas"]["StopwordBanResponse"];
export type StopwordRemovalResponse = components["schemas"]["StopwordRemovalResponse"];
export type StopwordPurgeResponse = components["schemas"]["StopwordPurgeResponse"];
export type TagMergeProposalDecisionResponse = components["schemas"]["TagMergeProposalDecisionResponse"];
export type TagMergeUndoResponse = components["schemas"]["TagMergeUndoResponse"];

// --- The named entities (NER): the relevance view, the merge and the vetoes --------------------
export type EntityRelevanceResponse = components["schemas"]["EntityRelevanceResponse"];
export type EntityPairSimilarity = components["schemas"]["EntityPairSimilarity"];
export type EntitySimilarity = components["schemas"]["EntitySimilarity"];
export type EntitySimilarityResponse = components["schemas"]["EntitySimilarityResponse"];
export type EntityMergeResponse = components["schemas"]["EntityMergeResponse"];
export type EntityMergeRequest = components["schemas"]["MergeRequest"];
export type ReclassifyEntityRequest = components["schemas"]["ReclassifyEntityRequest"];
export type EntityReclassifyResponse = components["schemas"]["EntityReclassifyResponse"];
export type EntityDeleteResponse = components["schemas"]["EntityDeleteResponse"];
export type OrphanEntityPurgeResponse = components["schemas"]["OrphanEntityPurgeResponse"];
export type NerExclusion = components["schemas"]["NerExclusion"];
export type NerExclusionBanResponse = components["schemas"]["NerExclusionBanResponse"];
export type NerExclusionRemovalResponse = components["schemas"]["NerExclusionRemovalResponse"];

/** An entity type the NER extractor is allowed to speak, taken from the route's own enum. */
export type EntityType = NonNullable<
  paths["/api/v1/taxonomy/entities/relevance"]["get"]["parameters"]["query"]
>["entity_type"];
export type ReclassifyTarget = ReclassifyEntityRequest["new_type"];

// --- The tag x entity collision (the LLM judge's queue) ----------------------------------------
export type CrossDomainConflict = components["schemas"]["CrossDomainConflict"];
export type CrossDomainConflictList = components["schemas"]["CrossDomainConflictListResponse"];
export type ConflictResolutionRequest = components["schemas"]["ConflictResolutionRequest"];
export type ConflictResolutionResponse = components["schemas"]["ConflictResolutionResponse"];
export type ConflictWinner = ConflictResolutionRequest["winner"];

// --- The subject vocabulary: exclusions and the cluster discovery ------------------------------
export type SubjectExclusionBanResponse = components["schemas"]["SubjectExclusionBanResponse"];
export type SubjectExclusionRemovalResponse = components["schemas"]["SubjectExclusionRemovalResponse"];
export type MacroCategorySuggested = components["schemas"]["MacroCategorySuggested"];
export type MacroCategoriesSuggestionResponse = components["schemas"]["MacroCategoriesSuggestionResponse"];

// --- Quality of the input data: excerpts, cleaning rules and the dry runs ----------------------
export type TextTemplate = components["schemas"]["TextTemplateDTO"];
export type TextTemplateMutationResponse = components["schemas"]["TextTemplateMutationResponse"];
export type TemplateDryRunResponse = components["schemas"]["TemplateDryRunResponse"];
export type TemplateDryRunMatch = components["schemas"]["TemplateDryRunMatch"];
export type TemplateSuggestionResponse = components["schemas"]["TemplateSuggestionResponse"];
export type TemplateSuggestion = components["schemas"]["TemplateSuggestion"];
export type CreateTextTemplateRequest = components["schemas"]["CreateTextTemplateRequest"];
export type UpdateTextTemplateRequest = components["schemas"]["UpdateTextTemplateRequest"];
export type DryRunTextTemplateRequest = components["schemas"]["DryRunTextTemplateRequest"];
export type CleaningRule = components["schemas"]["CleaningRuleDTO"];
export type CleaningRuleMutationResponse = components["schemas"]["CleaningRuleMutationResponse"];
export type CleaningRuleDryRun = components["schemas"]["DryRunResponseDTO"];
export type CleaningRuleDryRunMatch = components["schemas"]["DryRunMatchDTO"];
export type CreateCleaningRuleRequest = components["schemas"]["CreateCleaningRuleRequest"];
export type CleaningRuleDryRunRequest = components["schemas"]["DryRunRequest"];

/** What a rule does: rewrite the match, or only flag it. The difference is cleaning vs. destroying. */
export type RuleKind = NonNullable<CleaningRule["rule_kind"]>;
export type TemplateScope = NonNullable<TextTemplate["scope"]>[number];
export type TemplateStatus = NonNullable<TextTemplate["status"]>;
export type TemplateAction = NonNullable<TextTemplate["action"]>;
export type CleaningTargetColumn = CreateCleaningRuleRequest["target_column"];

// --- The arrangement: the ladder of levels and the materialised tree ---------------------------
export type DescriptionLevelCreateRequest = components["schemas"]["DescriptionLevelCreateRequest"];
export type DescriptionLevelUpdateRequest = components["schemas"]["DescriptionLevelUpdateRequest"];
export type HierarchyTree = components["schemas"]["HierarchyTreeResponse"];
export type HierarchyNodeDetail = components["schemas"]["HierarchyNodeDetail"];

/** Which verdict a proposal is waiting for, as the contract enumerates it. */
export type ProposalStatus = TagMergeProposal["status"];

/** The axis a term was banned from: the subject purge reads TAG/ALL, the NER extraction reads ENTITY. */
export type StopwordsScope = NonNullable<Stopword["scope"]>;

/**
 * How a cluster was formed, taken from the **request** the API accepts.
 *
 * The DTO carries ``reason`` as a plain string (it is read from storage), while the filter is an
 * enum — so deriving this from the DTO would give ``string`` and let the screen send a reason the
 * route refuses.
 */
export type MergeReason = NonNullable<
  paths["/api/v1/taxonomy/tags/merge-proposals"]["get"]["parameters"]["query"]
>["reason"];
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

/**
 * The ladder including the retired rungs.
 *
 * Deactivating a rung never deletes it and never moves the descriptions sitting on it, so the
 * catalog screen has to read them: without them the weight of the ladder looks smaller than it is.
 */
export async function fetchLevelCatalog(): Promise<DescriptionLevel[]> {
  return unwrap<DescriptionLevel[]>(
    await client.GET("/api/v1/hierarchy/levels", { params: { query: { only_active: false } } }),
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

// --- The subject vocabulary, seen as a whole: the drawers and the tag catalog ------------------

export async function createMacroCategory(body: MacroCategoryCreateRequest): Promise<MacroCategory> {
  return unwrap<MacroCategory>(await client.POST("/api/v1/taxonomy/macro-categories", { body }));
}

export async function updateMacroCategory(
  categoryId: number,
  body: MacroCategoryUpdateRequest,
): Promise<MacroCategory> {
  return unwrap<MacroCategory>(
    await client.PATCH("/api/v1/taxonomy/macro-categories/{category_id}", {
      params: { path: { category_id: categoryId } },
      body,
    }),
  );
}

/** Tags by weight: ``count`` counts usage, ``tfidf`` punishes what appears everywhere. */
export async function fetchTagRelevance(
  method: "count" | "tfidf",
  limit = 30,
): Promise<TagRelevanceResponse> {
  return unwrap<TagRelevanceResponse>(
    await client.GET("/api/v1/taxonomy/tags/relevance/{method}", {
      params: { path: { method }, query: { limit } },
    }),
  );
}

/**
 * Tag pairs by trigram similarity, or the neighbours of one tag.
 *
 * With no ``target`` the route returns **every** pair above the threshold, which is what the screen
 * shows: the pairs are the evidence a merge proposal is built from, and hiding them would make the
 * suggestion look arbitrary.
 */
export async function fetchSimilarTags(params: {
  target?: string;
  threshold?: number;
}): Promise<TagPairSimilarity[] | TagSimilarity[]> {
  return unwrap<TagPairSimilarity[] | TagSimilarity[]>(
    await client.GET("/api/v1/taxonomy/tags/similar", { params: { query: params } }),
  );
}

export async function fetchMergeProposals(params: {
  status?: ProposalStatus;
  /** The cluster's reason, as the contract enumerates it: TRIGRAM, PLURAL or MIXED. */
  reason?: MergeReason;
  min_documents?: number;
  flagged_only?: boolean;
  limit?: number;
  offset?: number;
}): Promise<TagMergeProposalList> {
  return unwrap<TagMergeProposalList>(
    await client.GET("/api/v1/taxonomy/tags/merge-proposals", { params: { query: params } }),
  );
}

/** Idempotent, and it never overwrites a verdict a human already recorded. */
export async function suggestMergeProposals(body: { threshold: number; limit: number }): Promise<MergeSuggestionRun> {
  return unwrap<MergeSuggestionRun>(await client.POST("/api/v1/taxonomy/tags/merge-proposals/suggest", { body }));
}

export async function decideMergeProposal(
  proposalId: number,
  body: MergeProposalDecision,
): Promise<TagMergeProposalDecisionResponse> {
  return unwrap<TagMergeProposalDecisionResponse>(
    await client.PATCH("/api/v1/taxonomy/tags/merge-proposals/{proposal_id}", {
      params: { path: { proposal_id: proposalId } },
      body,
    }),
  );
}

/** The dry run, computed by the same planner the merge executes. */
export async function previewMerge(proposalId: number): Promise<MergePreview> {
  return unwrap<MergePreview>(
    await client.POST("/api/v1/taxonomy/tags/merge/preview", { body: { proposal_id: proposalId } }),
  );
}

/** Applies the approved clusters, each in its own savepoint: one failure does not roll back the rest. */
export async function applyMergeBatch(body: {
  proposal_ids: number[];
  changed_by?: string | null;
  note?: string | null;
}): Promise<BatchMergeResponse> {
  return unwrap<BatchMergeResponse>(await client.POST("/api/v1/taxonomy/tags/merge/batch", { body }));
}

export async function fetchMergeLog(params: {
  include_undone?: boolean;
  limit?: number;
  offset?: number;
}): Promise<MergeLogList> {
  return unwrap<MergeLogList>(await client.GET("/api/v1/taxonomy/tags/merge-log", { params: { query: params } }));
}

/** Reverses one absorbed tag: the row, its links, its classification and its spellings. */
export async function undoMerge(mergeId: number, undoneBy?: string): Promise<TagMergeUndoResponse> {
  return unwrap<TagMergeUndoResponse>(
    await client.DELETE("/api/v1/taxonomy/tags/merge-log/{merge_id}", {
      params: { path: { merge_id: mergeId }, query: { undone_by: undoneBy ?? null } },
    }),
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

// --- The banned terms, and the one destructive write without an undo ---------------------------

/**
 * The banned terms, with the axis each was banned from.
 *
 * The query key is ``axis`` and not ``scope``: ``scope`` is reserved by the framework on the server
 * side, and the route's parameter had to be renamed — a route test caught the handler receiving the
 * raw request instead of the query value.
 */
export async function fetchStopwords(axis?: StopwordsScope): Promise<Stopword[]> {
  return unwrap<Stopword[]>(
    await client.GET("/api/v1/taxonomy/tags/stopwords", { params: { query: { axis } } }),
  );
}

/** Bans terms. Banning deletes nothing: the purge is a separate, explicit step. */
export async function banStopwords(body: {
  words: string[];
  scope?: StopwordsScope;
}): Promise<StopwordBanResponse> {
  return unwrap<StopwordBanResponse>(await client.POST("/api/v1/taxonomy/tags/stopwords", { body }));
}

/** Un-bans terms — the only way back from a purge decision, which has no ledger to restore from. */
export async function unbanStopwords(body: {
  words: string[];
  scope?: StopwordsScope;
}): Promise<StopwordRemovalResponse> {
  return unwrap<StopwordRemovalResponse>(await client.DELETE("/api/v1/taxonomy/tags/stopwords", { body }));
}

/** What the purge would delete. The step is mandatory: this write cannot be undone. */
export async function previewStopwordPurge(): Promise<StopwordPurgePreview> {
  return unwrap<StopwordPurgePreview>(await client.POST("/api/v1/taxonomy/tags/stopwords/purge/preview"));
}

/**
 * Deletes every tag whose name is a banned term.
 *
 * Sent with an empty body on purpose: registering words in the same call would make the numbers the
 * archivist approved different from the numbers that die.
 */
export async function purgeStopwords(): Promise<StopwordPurgeResponse> {
  return unwrap<StopwordPurgeResponse>(
    await client.POST("/api/v1/taxonomy/tags/stopwords/purge", { body: {} }),
  );
}

// --- The subject axis, second half: the terms that are not a subject at all --------------------

/** The curated half of ``NENHUMA``: terms no rule catches because the call is semantic. */
export async function fetchSubjectExclusions(): Promise<string[]> {
  return unwrap<string[]>(await client.GET("/api/v1/taxonomy/tags/subject-exclusions"));
}

export async function excludeFromSubjects(body: {
  words: string[];
  reason?: string | null;
}): Promise<SubjectExclusionBanResponse> {
  return unwrap<SubjectExclusionBanResponse>(
    await client.POST("/api/v1/taxonomy/tags/subject-exclusions", { body }),
  );
}

export async function restoreToSubjects(body: {
  words: string[];
}): Promise<SubjectExclusionRemovalResponse> {
  return unwrap<SubjectExclusionRemovalResponse>(
    await client.DELETE("/api/v1/taxonomy/tags/subject-exclusions", { body }),
  );
}

/**
 * Clusters the collection so a drawer the vocabulary lacks can be discovered.
 *
 * It drags the real clustering engine into the process, so it is a deliberate click and never a
 * page load. Below the engine's own floor it answers ``total_suggestions: 0`` with a message,
 * which is why the screen must render the message instead of an empty list.
 */
export async function suggestMacroCategories(body: {
  source_type: "tags" | "documents";
}): Promise<MacroCategoriesSuggestionResponse> {
  return unwrap<MacroCategoriesSuggestionResponse>(
    await client.POST("/api/v1/taxonomy/tags/suggest-macro", { body }),
  );
}

// --- The named entities: relevance, similarity, merge, reclassification and the vetoes ---------

export async function fetchEntityRelevance(params: {
  entity_type?: EntityType;
  limit?: number;
}): Promise<EntityRelevanceResponse> {
  return unwrap<EntityRelevanceResponse>(
    await client.GET("/api/v1/taxonomy/entities/relevance", { params: { query: params } }),
  );
}

/**
 * Entity pairs by trigram similarity, or the neighbours of one name.
 *
 * ``mode`` is what tells the two payloads apart: a single ``EntitySimilarity`` row is "these are
 * the neighbours of the name I asked about", a ``EntityPairSimilarity`` row is "these two are
 * alike". Rendering one as the other would invent a side that does not exist.
 */
export async function fetchSimilarEntities(params: {
  target_name?: string;
  entity_type?: EntityType;
  threshold?: number;
}): Promise<EntitySimilarityResponse> {
  return unwrap<EntitySimilarityResponse>(
    await client.GET("/api/v1/taxonomy/entities/similar", { params: { query: params } }),
  );
}

export async function mergeEntities(body: EntityMergeRequest): Promise<EntityMergeResponse> {
  return unwrap<EntityMergeResponse>(await client.POST("/api/v1/taxonomy/entities/merge", { body }));
}

/**
 * Changes an entity's type **and teaches the extractor**.
 *
 * It is not a label change: the service writes the anchoring synonym that makes the NER worker
 * obey the decision on every future run. The screen has to say that, or the archivist thinks they
 * renamed a row.
 */
export async function reclassifyEntity(
  entityId: number,
  body: ReclassifyEntityRequest,
): Promise<EntityReclassifyResponse> {
  return unwrap<EntityReclassifyResponse>(
    await client.PATCH("/api/v1/taxonomy/entities/{entity_id}/reclassify", {
      params: { path: { entity_id: entityId } },
      body,
    }),
  );
}

export async function deleteEntity(entityId: number): Promise<EntityDeleteResponse> {
  return unwrap<EntityDeleteResponse>(
    await client.DELETE("/api/v1/taxonomy/entities/{entity_id}", {
      params: { path: { entity_id: entityId } },
    }),
  );
}

/** Deletes the entities no description carries — the leftovers merges and deletions leave behind. */
export async function purgeOrphanEntities(): Promise<OrphanEntityPurgeResponse> {
  return unwrap<OrphanEntityPurgeResponse>(await client.POST("/api/v1/taxonomy/entities/orphans/purge"));
}

/** The terms the curation decided belong to the subject axis, not to NER. */
export async function fetchNerExclusions(): Promise<NerExclusion[]> {
  return unwrap<NerExclusion[]>(await client.GET("/api/v1/taxonomy/entities/ner-exclusions"));
}

/** Bans terms from NER and purges the entities already extracted from them. */
export async function banNerExclusions(body: {
  words: string[];
  reason?: string | null;
}): Promise<NerExclusionBanResponse> {
  return unwrap<NerExclusionBanResponse>(
    await client.POST("/api/v1/taxonomy/entities/ner-exclusions", { body }),
  );
}

export async function unbanNerExclusions(body: { words: string[] }): Promise<NerExclusionRemovalResponse> {
  return unwrap<NerExclusionRemovalResponse>(
    await client.DELETE("/api/v1/taxonomy/entities/ner-exclusions", { body }),
  );
}

// --- The tag x entity collision ----------------------------------------------------------------

export async function fetchCrossDomainConflicts(threshold = 0.85): Promise<CrossDomainConflictList> {
  return unwrap<CrossDomainConflictList>(
    await client.GET("/api/v1/taxonomy/conflicts/cross-domain", { params: { query: { threshold } } }),
  );
}

/**
 * Decides which side owns the spelling, and the answer is written to a different place per side.
 *
 * Entity wins -> the tag's name is banned from the subject axis; tag wins -> the term is recorded as
 * a NER exclusion with the tag that justifies it. The screen must say which one it is doing.
 */
export async function resolveConflict(body: ConflictResolutionRequest): Promise<ConflictResolutionResponse> {
  return unwrap<ConflictResolutionResponse>(await client.POST("/api/v1/taxonomy/conflicts/resolve", { body }));
}

// --- Quality of the input data: the repeated excerpts ------------------------------------------

export async function fetchTextTemplates(params: {
  status?: TemplateStatus;
  only_active?: boolean;
}): Promise<TextTemplate[]> {
  return unwrap<TextTemplate[]>(
    await client.GET("/api/v1/quality/text-templates", { params: { query: params } }),
  );
}

export async function createTextTemplate(body: CreateTextTemplateRequest): Promise<TextTemplateMutationResponse> {
  return unwrap<TextTemplateMutationResponse>(
    await client.POST("/api/v1/quality/text-templates", { body }),
  );
}

export async function updateTextTemplate(
  templateId: number,
  body: UpdateTextTemplateRequest,
): Promise<TextTemplateMutationResponse> {
  return unwrap<TextTemplateMutationResponse>(
    await client.PATCH("/api/v1/quality/text-templates/{template_id}", {
      params: { path: { template_id: templateId } },
      body,
    }),
  );
}

/** Undoes the decision and puts every document the excerpt touched back in the AI queue. */
export async function deleteTextTemplate(templateId: number): Promise<TextTemplateMutationResponse> {
  return unwrap<TextTemplateMutationResponse>(
    await client.DELETE("/api/v1/quality/text-templates/{template_id}", {
      params: { path: { template_id: templateId } },
    }),
  );
}

/**
 * Scans the collection for repeated excerpts and registers them as suggestions.
 *
 * The thresholds are the engine's own: how much of the collection a block must cover to be worth
 * proposing. Nothing is applied to the AI text before a human approves it.
 */
export async function suggestTextTemplates(body: {
  min_ratio: number;
  min_documents: number;
}): Promise<TemplateSuggestionResponse> {
  return unwrap<TemplateSuggestionResponse>(
    await client.POST("/api/v1/quality/text-templates/suggest", { body }),
  );
}

export async function previewTextTemplate(
  body: DryRunTextTemplateRequest,
): Promise<TemplateDryRunResponse> {
  return unwrap<TemplateDryRunResponse>(
    await client.POST("/api/v1/quality/text-templates/preview", { body }),
  );
}

// --- Quality of the input data: the cleaning rules ---------------------------------------------

export async function fetchCleaningRules(): Promise<CleaningRule[]> {
  return unwrap<CleaningRule[]>(await client.GET("/api/v1/quality/cleaning-rules"));
}

export async function createCleaningRule(
  body: CreateCleaningRuleRequest,
): Promise<CleaningRuleMutationResponse> {
  return unwrap<CleaningRuleMutationResponse>(
    await client.POST("/api/v1/quality/cleaning-rules", { body }),
  );
}

/** Rules are never deleted: deactivating is the reversible way to stop the worker reading them. */
export async function deactivateCleaningRule(ruleId: number): Promise<CleaningRuleMutationResponse> {
  return unwrap<CleaningRuleMutationResponse>(
    await client.PATCH("/api/v1/quality/cleaning-rules/{rule_id}/deactivate", {
      params: { path: { rule_id: ruleId } },
    }),
  );
}

/** Before/after of the matches, computed without writing anything. The step before creating a rule. */
export async function previewCleaningRule(body: CleaningRuleDryRunRequest): Promise<CleaningRuleDryRun> {
  return unwrap<CleaningRuleDryRun>(
    await client.POST("/api/v1/quality/cleaning-rules/preview", { body }),
  );
}

// --- The arrangement: the ladder and the materialised tree -------------------------------------

export async function createLevel(body: DescriptionLevelCreateRequest): Promise<DescriptionLevel> {
  return unwrap<DescriptionLevel>(await client.POST("/api/v1/hierarchy/levels", { body }));
}

/**
 * Partial edit of a rung. ``ordinal`` is absent on purpose: re-ranking the ladder would silently
 * renumber the tree, so the route does not accept it.
 */
export async function updateLevel(
  levelId: number,
  body: DescriptionLevelUpdateRequest,
): Promise<DescriptionLevel> {
  return unwrap<DescriptionLevel>(
    await client.PATCH("/api/v1/hierarchy/levels/{level_id}", {
      params: { path: { level_id: levelId } },
      body,
    }),
  );
}

/**
 * The arrangement, flat and ordered by path.
 *
 * ``root_id`` asks for one subtree (an indexed prefix of the materialised path), ``max_depth`` how
 * far below it to go. The screen builds the indentation from ``path``/``parent_id``; the API does
 * not return nested children, because a subtree read is one query and not a walk per level.
 */
export async function fetchHierarchyTree(params: {
  root_id?: string;
  max_depth?: number;
  limit?: number;
  offset?: number;
}): Promise<HierarchyTree> {
  return unwrap<HierarchyTree>(
    await client.GET("/api/v1/hierarchy/tree", { params: { query: params } }),
  );
}

export async function fetchHierarchyNode(descriptionId: string): Promise<HierarchyNodeDetail> {
  return unwrap<HierarchyNodeDetail>(
    await client.GET("/api/v1/hierarchy/nodes/{description_id}", {
      params: { path: { description_id: descriptionId } },
    }),
  );
}
