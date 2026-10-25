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
    /**
     * The request id the API answered with. Every response carries one, so an archivist reporting
     * "this screen broke" hands over the exact line to find in the server log; without it the
     * report is a time range and an eyeball.
     */
    readonly ref?: string,
    /**
     * The refusal's facts, when it has any. ``undefined`` for a refusal that is only a sentence.
     *
     * The API's sentence is Portuguese and the interface is going to be translated (#45), so a screen
     * that has to name *which* twin a rename collided with reads the pair here and wraps it in
     * `lib/messages.ts`'s copy. The error body is declared by no route, so this field is read by hand:
     * the generated client cannot type what the contract does not describe.
     */
    readonly details?: Record<string, unknown>,
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
    const payload = result.error as {
      error_code?: string;
      message?: string;
      detail?: string;
      details?: Record<string, unknown>;
    } | null;
    throw new ApiError(
      result.response.status,
      payload?.error_code ?? "UNKNOWN",
      payload?.message ?? payload?.detail ?? `Erro ${result.response.status}`,
      result.response.headers.get("X-Request-ID") ?? undefined,
      payload?.details,
    );
  }
  return result.data as T;
}

export type AuthUser = components["schemas"]["AuthUserDTO"];
export type RouteResponse = components["schemas"]["RouteResponse"];
/** The one fact the API tells an anonymous client about the installation (ADR 0011). */
export type SetupStatusResponse = components["schemas"]["SetupStatusResponse"];

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
export type DocumentDeletion = components["schemas"]["DocumentDeletionDTO"];
export type DocumentDeletionList = components["schemas"]["DocumentDeletionListResponse"];
export type DocumentDeletionResponse = components["schemas"]["DocumentDeletionResponse"];
export type DescriptionLevel = components["schemas"]["DescriptionLevelDTO"];
export type ArchiveReviewStatus = components["schemas"]["ArchiveReviewStatus"];
export type DocumentUpdateRequest = components["schemas"]["DocumentUpdateRequest"];

// --- The documental typologies: the diplomatic form of a record --------------------------------
export type Typology = components["schemas"]["TypologyDTO"];
export type TypologyCreateRequest = components["schemas"]["TypologyCreateRequest"];
export type TypologyUpdateRequest = components["schemas"]["TypologyUpdateRequest"];
export type TypologyRefusalRow = components["schemas"]["TypologyRefusalRow"];
export type TypologyRefusalList = components["schemas"]["TypologyRefusalListResponse"];

// --- The collection vocabulary: what this archive declares, as opposed to the language ----------
export type CollectionVocabulary = components["schemas"]["CollectionVocabularyResponse"];
export type ArrangementTerm = components["schemas"]["ArrangementTermDTO"];
export type CollectionTerm = components["schemas"]["CollectionTermDTO"];
export type CollectionTermKind = components["schemas"]["CollectionTermKind"];
export type ArrangementTermCreateRequest = components["schemas"]["ArrangementTermCreateRequest"];
export type ArrangementTermUpdateRequest = components["schemas"]["ArrangementTermUpdateRequest"];
export type CollectionTermCreateRequest = components["schemas"]["CollectionTermCreateRequest"];
export type CollectionTermUpdateRequest = components["schemas"]["CollectionTermUpdateRequest"];

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
export type TagCatalogState = components["schemas"]["TagCatalogState"];
export type TagCatalogResponse = components["schemas"]["TagCatalogResponse"];
export type TagCatalogRow = components["schemas"]["TagCatalogRow"];
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
/**
 * The merge request bodies, named so a call takes the model its route declares (#93).
 *
 * A body typed out in the signature is the same second definition the query shapes were, and it
 * fails the same silent way: pydantic refuses a missing *required* field but ignores an unknown
 * one, so a renamed optional field is dropped without a trace. Only deriving can rule that out.
 */
export type MergeSuggestionRequest = components["schemas"]["MergeSuggestionRequest"];
export type MergeBatchRequest = components["schemas"]["MergeBatchRequest"];
export type MergePreviewRequest = components["schemas"]["MergePreviewRequest"];
export type Stopword = components["schemas"]["StopwordDTO"];
export type StopwordMatch = NonNullable<Stopword["match_mode"]>;
export type StopwordPurgePreview = components["schemas"]["StopwordPurgePreview"];
export type StopwordPurgeTag = components["schemas"]["StopwordPurgeTag"];
export type StopwordBanResponse = components["schemas"]["StopwordBanResponse"];
export type StopwordMatchResponse = components["schemas"]["StopwordMatchResponse"];
export type StopwordRemovalResponse = components["schemas"]["StopwordRemovalResponse"];
export type StopwordPurgeResponse = components["schemas"]["StopwordPurgeResponse"];
export type StopwordPurgeLogEntryDTO = components["schemas"]["StopwordPurgeLogEntryDTO"];
export type StopwordPurgeLogListResponse = components["schemas"]["StopwordPurgeLogListResponse"];
export type StopwordPurgeUndoResponse = components["schemas"]["StopwordPurgeUndoResponse"];
export type StopwordCreateRequest = components["schemas"]["StopwordCreateRequest"];
export type StopwordMatchRequest = components["schemas"]["StopwordMatchRequest"];
export type StopwordRemovalRequest = components["schemas"]["StopwordRemovalRequest"];
export type TagMergeProposalDecisionResponse = components["schemas"]["TagMergeProposalDecisionResponse"];
export type TagMergeUndoResponse = components["schemas"]["TagMergeUndoResponse"];

// --- The named entities (NER): the relevance view, the merge and the vetoes --------------------
export type EntityRelevanceResponse = components["schemas"]["EntityRelevanceResponse"];
export type EntityPairSimilarity = components["schemas"]["EntityPairSimilarity"];
export type EntitySimilarity = components["schemas"]["EntitySimilarity"];
export type EntitySimilarityResponse = components["schemas"]["EntitySimilarityResponse"];
export type EntityMergeResponse = components["schemas"]["EntityMergeResponse"];
export type EntityMergePreviewResponse = components["schemas"]["EntityMergePreviewResponse"];
export type EntityMergeImpact = components["schemas"]["EntityMergeImpact"];
export type EntityMergeLogList = components["schemas"]["EntityMergeLogListResponse"];
export type EntityMergeLogEntry = components["schemas"]["EntityMergeLogEntryDTO"];
export type EntityMergeUndoResponse = components["schemas"]["EntityMergeUndoResponse"];

/**
 * One canonical row absorbing the others — the payload both vocabularies accept.
 *
 * Tags and entities share the shape on purpose: the operation is the same, and the front should not
 * learn a second spelling of "merge these two". The entity route adds ``note``, which the tag route
 * does not record.
 */
export type MergeRequest = components["schemas"]["MergeRequest"];
export type EntityMergeRequest = components["schemas"]["EntityMergeRequest"];
export type ReclassifyEntityRequest = components["schemas"]["ReclassifyEntityRequest"];
export type EntityReclassifyResponse = components["schemas"]["EntityReclassifyResponse"];
export type EntityDeleteResponse = components["schemas"]["EntityDeleteResponse"];
export type EntityRenameRequest = components["schemas"]["EntityRenameRequest"];
export type EntityRenameResponse = components["schemas"]["EntityRenameResponse"];
export type EntityMergePreviewRequest = components["schemas"]["EntityMergePreviewRequest"];
export type OrphanEntityPurgeResponse = components["schemas"]["OrphanEntityPurgeResponse"];
export type NerExclusion = components["schemas"]["NerExclusion"];
export type NerExclusionRequest = components["schemas"]["NerExclusionRequest"];
export type NerExclusionRemovalRequest = components["schemas"]["NerExclusionRemovalRequest"];
export type NerExclusionBanResponse = components["schemas"]["NerExclusionBanResponse"];
export type NerExclusionRemovalResponse = components["schemas"]["NerExclusionRemovalResponse"];
export type NerPurgeEntity = components["schemas"]["NerPurgeEntity"];
export type NerPurgePreview = components["schemas"]["NerPurgePreview"];
export type NerPurgeResponse = components["schemas"]["NerPurgeResponse"];
export type NerPurgeLogEntryDTO = components["schemas"]["NerPurgeLogEntryDTO"];
export type NerPurgeLogListResponse = components["schemas"]["NerPurgeLogListResponse"];
export type NerPurgeUndoResponse = components["schemas"]["NerPurgeUndoResponse"];

/** An entity type the NER extractor is allowed to speak, taken from the route's own enum. */
export type EntityType = NonNullable<
  paths["/api/v1/taxonomy/entities/relevance"]["get"]["parameters"]["query"]
>["entity_type"];
export type ReclassifyTarget = ReclassifyEntityRequest["new_type"];

// --- The tag x entity collision (the LLM judge's queue) ----------------------------------------
export type CrossDomainConflict = components["schemas"]["CrossDomainConflict"];
export type CrossDomainConflictPage = components["schemas"]["CrossDomainConflictPage"];
export type JudgedConflict = components["schemas"]["JudgedConflict"];
export type JudgedConflictPage = components["schemas"]["JudgedConflictPage"];
export type ConflictResolutionPlan = components["schemas"]["ConflictResolutionPlan"];
export type ConflictResolutionLogEntry = components["schemas"]["ConflictResolutionLogEntry"];
export type ConflictResolutionLogList = components["schemas"]["ConflictResolutionLogListResponse"];
export type ConflictResolutionRequest = components["schemas"]["ConflictResolutionRequest"];
export type ConflictPreviewRequest = components["schemas"]["ConflictPreviewRequest"];
export type ConflictResolutionResponse = components["schemas"]["ConflictResolutionResponse"];
export type ConflictBatchRequest = components["schemas"]["ConflictBatchRequest"];
export type ConflictBatchResponse = components["schemas"]["ConflictBatchResponse"];
export type ConflictBatchResult = components["schemas"]["ConflictBatchResult"];
export type ConflictWinner = ConflictResolutionRequest["winner"];
export type ConflictDecider = ConflictResolutionLogEntry["source"];
/** Which of the two populations a pair belongs to: the same spelling, or the same word written twice. */
export type ConflictPairKind = CrossDomainConflict["pair_kind"];
/**
 * The *filter* vocabulary of the live list.
 *
 * Deliberately not the same type as {@link ConflictPairKind}: the DTO states the pair's kind in
 * the payload (``EXACT_NAME``), while the query string selects a population (``exact_name``,
 * plus ``all``). One is a fact about a pair, the other is what the archivist asked to see.
 */
export type ConflictPairKindFilter = "all" | "exact_name" | "near_duplicate";

// --- The subject vocabulary: exclusions and the agrupamento discovery ------------------------------
export type SubjectExclusionBanResponse = components["schemas"]["SubjectExclusionBanResponse"];
export type SubjectExclusionPreviewRequest = components["schemas"]["SubjectExclusionPreviewRequest"];
export type SubjectExclusionPlan = components["schemas"]["SubjectExclusionPlan"];
export type SubjectExclusionRequest = components["schemas"]["SubjectExclusionRequest"];
export type SubjectExclusionRemovalRequest = components["schemas"]["SubjectExclusionRemovalRequest"];
export type SubjectExclusionSuggestion = components["schemas"]["SubjectExclusionSuggestion"];
export type SubjectExclusionSuggestionResponse =
  components["schemas"]["SubjectExclusionSuggestionResponse"];
export type SubjectExclusionRemovalResponse = components["schemas"]["SubjectExclusionRemovalResponse"];
export type MacroCategorySuggested = components["schemas"]["MacroCategorySuggested"];
export type MacroCategoriesSuggestionResponse = components["schemas"]["MacroCategoriesSuggestionResponse"];
export type ClusteringColumnsResponse = components["schemas"]["ClusteringColumnsResponse"];
export type SuggestMacroRequest = components["schemas"]["SuggestMacroRequest"];

// --- Quality of the input data: excerpts, cleaning rules and the dry runs ----------------------
export type TextTemplate = components["schemas"]["TextTemplateDTO"];
export type TextTemplateMutationResponse = components["schemas"]["TextTemplateMutationResponse"];
export type TemplateDryRunResponse = components["schemas"]["TemplateDryRunResponse"];
export type TemplateDryRunMatch = components["schemas"]["TemplateDryRunMatch"];
export type TemplateSuggestionResponse = components["schemas"]["TemplateSuggestionResponse"];
export type TemplateSuggestion = components["schemas"]["TemplateSuggestion"];
export type CreateTextTemplateRequest = components["schemas"]["CreateTextTemplateRequest"];
export type SuggestTextTemplatesRequest = components["schemas"]["SuggestTextTemplatesRequest"];
export type UpdateTextTemplateRequest = components["schemas"]["UpdateTextTemplateRequest"];
export type DryRunTextTemplateRequest = components["schemas"]["DryRunTextTemplateRequest"];
export type CleaningRule = components["schemas"]["CleaningRuleDTO"];
export type CleaningRuleMutationResponse = components["schemas"]["CleaningRuleMutationResponse"];
export type CleaningRuleDryRun = components["schemas"]["DryRunResponseDTO"];
export type CleaningRuleDryRunMatch = components["schemas"]["DryRunMatchDTO"];
export type CreateCleaningRuleRequest = components["schemas"]["CreateCleaningRuleRequest"];
export type CleaningRuleDryRunRequest = components["schemas"]["DryRunRequest"];

/**
 * One engine an `LLM_CHECK` rule can name, with the presets it declares.
 *
 * The same shape the operations panel reads per worker: the catalogue is the registry's, so the
 * screen offers the names `get_engine` accepts instead of asking a person to remember them (#124).
 */
export type CleaningRuleEngine = components["schemas"]["WorkerEngineDTO"];
export type CleaningRulePreset = components["schemas"]["WorkerPresetDTO"];

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
 * How a agrupamento was formed, taken from the **request** the API accepts.
 *
 * The DTO carries ``reason`` as a plain string (it is read from storage), while the filter is an
 * enum — so deriving this from the DTO would give ``string`` and let the screen send a reason the
 * route refuses.
 */
export type MergeReason = NonNullable<
  NonNullable<paths["/api/v1/taxonomy/tags/merge-proposals"]["get"]["parameters"]["query"]>["reason"]
>;
export type HierarchyNodeMoveRequest = components["schemas"]["HierarchyNodeMoveRequest"];
export type HierarchyNodeCreateRequest = components["schemas"]["HierarchyNodeCreateRequest"];
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

// --- The operations panel: the AI workers, their configuration and the execution ledger --------

export type SystemWorkers = components["schemas"]["SystemWorkersResponse"];
export type SystemWorkerSettings = components["schemas"]["SystemWorkerSettingsResponse"];
export type WorkerSettingsItem = components["schemas"]["WorkerSettingsItemDTO"];
export type WorkerStatus = components["schemas"]["WorkerStatusDTO"];
export type WorkerRunner = components["schemas"]["WorkerRunnerDTO"];
export type WorkerSettings = components["schemas"]["WorkerSettingsDTO"];
export type WorkerSettingsRequest = components["schemas"]["WorkerSettingsRequest"];
export type WorkerSchedule = components["schemas"]["WorkerScheduleDTO"];
export type WorkerScheduleRequest = components["schemas"]["WorkerScheduleRequest"];
export type WorkerQueuePreview = components["schemas"]["WorkerQueuePreviewDTO"];
export type WorkerSettingsRevision = components["schemas"]["WorkerSettingsRevisionDTO"];
export type WorkerSettingsRevisionList = components["schemas"]["WorkerSettingsRevisionListResponse"];
export type WorkerEngine = components["schemas"]["WorkerEngineDTO"];
export type WorkerPreset = components["schemas"]["WorkerPresetDTO"];
export type WorkerOption = components["schemas"]["WorkerOptionDTO"];
export type WorkerRun = components["schemas"]["WorkerRunDTO"];
export type WorkerRunList = components["schemas"]["WorkerRunListResponse"];
export type FailureGroup = components["schemas"]["FailureGroupDTO"];
export type FailureGroupList = components["schemas"]["FailureGroupListResponse"];
export type FailureSource = components["schemas"]["FailureSource"];
export type WorkerRunRequest = components["schemas"]["WorkerRunRequest"];
export type SystemHealth = components["schemas"]["SystemHealthResponse"];
export type DatabaseHealth = components["schemas"]["DatabaseHealthDTO"];
export type OllamaHealth = components["schemas"]["OllamaHealthDTO"];
export type StorageHealth = components["schemas"]["StorageHealthDTO"];
export type ProcessHealth = components["schemas"]["ProcessHealthDTO"];

/** The run lifecycle, as the contract enumerates it (never a second copy of the vocabulary). */
export type WorkerRunStatus = WorkerRun["status"];

/**
 * Where a worker's engine comes from, which is what the screen may offer.
 *
 * ``signature``: engine and preset are editable here. ``llm_check_rule``: the engine lives in the
 * cleaning rule, so the editor must not pretend to own it. ``none``: no model at all.
 */
export type EngineSource = WorkerSettings["engine_source"];

/**
 * Every filter the collection search accepts; they all live in the URL.
 *
 * **Derived from the contract, where it used to be written by hand.** The generated type already
 * spells an omitted filter the way a caller hands one over — `is_anomaly?: boolean | null` — so the
 * derivation is the type itself and there is nothing to reinterpret.
 *
 * The object it replaced declared fourteen keys against the route's fifteen: it had lost
 * `is_anomaly`, and nothing failed, because ``CollectionRoute.toRequest`` spreads its own
 * ``CollectionSearch`` into it and the extra key survives the return type, so `openapi-fetch` kept
 * sending a filter the type said did not exist. The failure it was hiding is silent in the worst
 * direction: an unknown query parameter is *ignored* and the route answers 200 with the whole set, so
 * a contract that renamed `is_anomaly` would leave the list unfiltered with a chip on the screen
 * saying it was filtered, and `tsc`, ESLint, the build and the suite all green.
 * ``testing/unit/curator/test_api_query_shapes.py`` is the gate that keeps the next one derived.
 */
export type DocumentSearch = NonNullable<paths["/api/v1/documents"]["get"]["parameters"]["query"]>;

/** The ranking mode, as the contract enumerates it and not as a second copy of the vocabulary. */
export type SearchMode = NonNullable<DocumentSearch["mode"]>;

/** The tag catalogue's filters: the contract's, for the same reason as the collection search's. */
export type TagCatalogSearch = NonNullable<paths["/api/v1/taxonomy/tags/catalog"]["get"]["parameters"]["query"]>;

/** The refusal queue's pagination, derived from the route that answers it. */
export type TypologyRefusalSearch = NonNullable<
  paths["/api/v1/typologies/refusals"]["get"]["parameters"]["query"]
>;

/** The merge-proposal filters, derived from the route that reads them. */
export type MergeProposalSearch = NonNullable<
  paths["/api/v1/taxonomy/tags/merge-proposals"]["get"]["parameters"]["query"]
>;

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

/**
 * Deletes one description for good.
 *
 * The only write in the front that removes a record. The API refuses a node that still has children
 * (the arrangement's FK is ``RESTRICT``) and answers 409; the screen has to show that message, because
 * "exclua ou mova os filhos primeiro" is the whole answer to the click.
 */
export async function deleteDocument(
  descriptionId: string,
  params: { note?: string | null } = {},
): Promise<DocumentDeletionResponse> {
  return unwrap<DocumentDeletionResponse>(
    await client.DELETE("/api/v1/documents/{description_id}", {
      params: {
        path: { description_id: descriptionId },
        query: { note: params.note ?? null },
      },
    }),
  );
}

/**
 * The deletion ledger: what was removed, when, by whom, and the snapshot of it.
 *
 * ``term`` is matched server-side against reference code, title and id, because the trail grows
 * without bound and a client-side filter would only ever see the page it was given.
 */
export async function fetchDeletions(
  params: NonNullable<paths["/api/v1/documents/deletions"]["get"]["parameters"]["query"]>,
): Promise<DocumentDeletionList> {
  return unwrap<DocumentDeletionList>(
    await client.GET("/api/v1/documents/deletions", { params: { query: params } }),
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

/**
 * The typologies the classifier may propose, for the dossier's select.
 *
 * Active only: a retired typology is not a candidate anymore, so offering it in the description's
 * editor would invite a classification the catalogue just decided against.
 */
export async function fetchTypologies(): Promise<Typology[]> {
  return unwrap<Typology[]>(
    await client.GET("/api/v1/typologies", { params: { query: { only_active: true } } }),
  );
}

/**
 * The whole typology catalogue, retired ones included.
 *
 * Deactivating never deletes and never unclassifies, so the catalogue screen has to read them: the
 * descriptions carrying a retired typology are exactly the weight that makes retiring a trade.
 */
export async function fetchTypologyCatalog(): Promise<Typology[]> {
  return unwrap<Typology[]>(
    await client.GET("/api/v1/typologies", { params: { query: { only_active: false } } }),
  );
}

/**
 * One page of the descriptions the typology classifier refused, nearest miss first.
 *
 * The evidence is the queue row the run wrote; filing one is the dossier's ``updateDocument`` with
 * a ``typology_id``, so this read is the only new seam.
 */
export async function fetchTypologyRefusals(params: TypologyRefusalSearch): Promise<TypologyRefusalList> {
  return unwrap<TypologyRefusalList>(
    await client.GET("/api/v1/typologies/refusals", { params: { query: params } }),
  );
}

export async function createTypology(body: TypologyCreateRequest): Promise<Typology> {
  return unwrap<Typology>(await client.POST("/api/v1/typologies", { body }));
}

/** Partial edit. There is no delete: ``is_active=false`` is what retires a typology. */
export async function updateTypology(
  typologyId: number,
  body: TypologyUpdateRequest,
): Promise<Typology> {
  return unwrap<Typology>(
    await client.PATCH("/api/v1/typologies/{typology_id}", {
      params: { path: { typology_id: typologyId } },
      body,
    }),
  );
}

// --- The collection vocabulary -----------------------------------------------------------------

/** Both catalogues in one read: the screen shows them together. */
export async function fetchCollectionVocabulary(): Promise<CollectionVocabulary> {
  return unwrap<CollectionVocabulary>(await client.GET("/api/v1/vocabulary"));
}

export async function createArrangementTerm(
  body: ArrangementTermCreateRequest,
): Promise<ArrangementTerm> {
  return unwrap<ArrangementTerm>(
    await client.POST("/api/v1/vocabulary/arrangement-terms", { body }),
  );
}

/** Partial edit. There is no delete: ``is_active=false`` retires the suggestion. */
export async function updateArrangementTerm(
  termId: number,
  body: ArrangementTermUpdateRequest,
): Promise<ArrangementTerm> {
  return unwrap<ArrangementTerm>(
    await client.PATCH("/api/v1/vocabulary/arrangement-terms/{term_id}", {
      params: { path: { term_id: termId } },
      body,
    }),
  );
}

export async function createCollectionTerm(
  body: CollectionTermCreateRequest,
): Promise<CollectionTerm> {
  return unwrap<CollectionTerm>(await client.POST("/api/v1/vocabulary/collection-terms", { body }));
}

/** Partial edit. There is no delete: ``is_active=false`` retires the term. */
export async function updateCollectionTerm(
  termId: number,
  body: CollectionTermUpdateRequest,
): Promise<CollectionTerm> {
  return unwrap<CollectionTerm>(
    await client.PATCH("/api/v1/vocabulary/collection-terms/{term_id}", {
      params: { path: { term_id: termId } },
      body,
    }),
  );
}

export async function linkTag(descriptionId: string, tagId: number): Promise<DocumentSummary> {
  return unwrap<DocumentSummary>(
    await client.POST("/api/v1/documents/{description_id}/tags", {
      params: { path: { description_id: descriptionId } },
      body: { tag_id: tagId, review_note: null },
    }),
  );
}

export async function unlinkTag(descriptionId: string, tagId: number): Promise<DocumentSummary> {
  return unwrap<DocumentSummary>(
    await client.DELETE("/api/v1/documents/{description_id}/tags/{tag_id}", {
      params: {
        path: { description_id: descriptionId, tag_id: tagId },
        query: { review_note: null },
      },
    }),
  );
}

export async function unlinkEntity(descriptionId: string, entityId: number): Promise<DocumentSummary> {
  return unwrap<DocumentSummary>(
    await client.DELETE("/api/v1/documents/{description_id}/entities/{entity_id}", {
      params: {
        path: { description_id: descriptionId, entity_id: entityId },
        query: { review_note: null },
      },
    }),
  );
}

export async function linkEntity(descriptionId: string, entityId: number): Promise<DocumentSummary> {
  return unwrap<DocumentSummary>(
    await client.POST("/api/v1/documents/{description_id}/entities", {
      params: { path: { description_id: descriptionId } },
      body: { entity_id: entityId, review_note: null },
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

/**
 * One page of the tag catalogue, filtered by the state of the subject decision.
 *
 * The read the home screen's cards land on: the type-ahead cannot answer "list the tags nobody has
 * decided about", because it requires a term and returns a top-N by weight.
 */
export async function fetchTagCatalog(params: TagCatalogSearch): Promise<TagCatalogResponse> {
  return unwrap<TagCatalogResponse>(
    await client.GET("/api/v1/taxonomy/tags/catalog", { params: { query: params } }),
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
export async function fetchSimilarTags(
  params: NonNullable<paths["/api/v1/taxonomy/tags/similar"]["get"]["parameters"]["query"]>,
): Promise<TagPairSimilarity[] | TagSimilarity[]> {
  return unwrap<TagPairSimilarity[] | TagSimilarity[]>(
    await client.GET("/api/v1/taxonomy/tags/similar", { params: { query: params } }),
  );
}

export async function fetchMergeProposals(params: MergeProposalSearch): Promise<TagMergeProposalList> {
  return unwrap<TagMergeProposalList>(
    await client.GET("/api/v1/taxonomy/tags/merge-proposals", { params: { query: params } }),
  );
}

/** Idempotent, and it never overwrites a verdict a human already recorded. */
export async function suggestMergeProposals(body: MergeSuggestionRequest): Promise<MergeSuggestionRun> {
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

/** Applies the approved agrupamentos, each in its own savepoint: one failure does not roll back the rest. */
export async function applyMergeBatch(body: MergeBatchRequest): Promise<BatchMergeResponse> {
  return unwrap<BatchMergeResponse>(await client.POST("/api/v1/taxonomy/tags/merge/batch", { body }));
}

/**
 * The merge ledger, optionally filtered by a term.
 *
 * ``q`` is matched **server-side against both sides** of each entry — the absorbed and the canonical
 * name — because "where did this spelling go?" does not say which side it was on, and the trail grows
 * without bound: a filter over the loaded page would answer "não está aqui" for a row that is.
 */
export async function fetchMergeLog(
  params: NonNullable<paths["/api/v1/taxonomy/tags/merge-log"]["get"]["parameters"]["query"]>,
): Promise<MergeLogList> {
  return unwrap<MergeLogList>(await client.GET("/api/v1/taxonomy/tags/merge-log", { params: { query: params } }));
}

/** Reverses one absorbed tag: the row, its links, its classification and its spellings. */
export async function undoMerge(mergeId: number): Promise<TagMergeUndoResponse> {
  return unwrap<TagMergeUndoResponse>(
    await client.DELETE("/api/v1/taxonomy/tags/merge-log/{merge_id}", {
      params: { path: { merge_id: mergeId } },
    }),
  );
}

/**
 * The pair form of the merge preview, and only it: the proposal form is ``previewMerge``'s.
 *
 * Both keys stay required because the model's validator requires exactly one source of truth, so
 * omitting them is a 400 and not a default. ``proposal_id`` is left out for the opposite reason: a
 * function called "pair" that also accepted a proposal would be advertising two ways to call it.
 */
type TagPairPreviewBody = Required<Pick<MergePreviewRequest, "canonical_id" | "ids_to_merge">>;

/**
 * The dry run for a pair the archivist chose by hand.
 *
 * The proposal flow previews by ``proposal_id``; here the pair comes from the similarity list, which
 * is the raw evidence and carries no proposal. The same endpoint answers both, and one planner
 * computes both — so the numbers shown are the numbers the write produces.
 */
export async function previewTagPair(body: TagPairPreviewBody): Promise<MergePreview> {
  return unwrap<MergePreview>(await client.POST("/api/v1/taxonomy/tags/merge/preview", { body }));
}

/**
 * Merges tags the archivist selected, without going through a proposal.
 *
 * Reversible on purpose: the write lands in ``archive_taxonomy_merge_log`` and
 * ``DELETE /tags/merge-log/{merge_id}`` restores the tag, its links, its classification and the
 * spellings earlier merges had absorbed. That is the difference from the entity merge, which has no
 * ledger — and the reason this screen can offer the button the entity screen offers with a warning.
 */
export async function mergeTags(body: MergeRequest): Promise<MergeResponse> {
  return unwrap<MergeResponse>(await client.POST("/api/v1/taxonomy/tags/merge", { body }));
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

export async function fetchHierarchyPlans(
  params: NonNullable<paths["/api/v1/hierarchy/plans"]["get"]["parameters"]["query"]>,
): Promise<HierarchyPlanList> {
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

/** The materialisation ledger, filtered by author or note — the two fields a run is recognised by. */
export async function fetchMaterialisationLog(
  params: NonNullable<paths["/api/v1/hierarchy/materialisation/log"]["get"]["parameters"]["query"]>,
): Promise<MaterialisationLog> {
  return unwrap<MaterialisationLog>(
    await client.GET("/api/v1/hierarchy/materialisation/log", { params: { query: params } }),
  );
}

/** Reverses one run from the ledger. The ledger entry survives, with ``undone_at`` set. */
export async function undoMaterialisation(materialisationId: number): Promise<void> {
  await unwrap<unknown>(
    await client.DELETE("/api/v1/hierarchy/materialisation/log/{materialisation_id}", {
      params: { path: { materialisation_id: materialisationId } },
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
export async function banStopwords(body: StopwordCreateRequest): Promise<StopwordBanResponse> {
  return unwrap<StopwordBanResponse>(await client.POST("/api/v1/taxonomy/tags/stopwords", { body }));
}

/** Changes how existing bans match, keeping their axis and who planted them. */
export async function setStopwordMatch(body: StopwordMatchRequest): Promise<StopwordMatchResponse> {
  return unwrap<StopwordMatchResponse>(await client.PATCH("/api/v1/taxonomy/tags/stopwords", { body }));
}

/** Un-bans terms. The purge keeps a ledger, so this is no longer the only way back. */
export async function unbanStopwords(body: StopwordRemovalRequest): Promise<StopwordRemovalResponse> {
  return unwrap<StopwordRemovalResponse>(await client.DELETE("/api/v1/taxonomy/tags/stopwords", { body }));
}

/** What the purge would delete, and the confirmation that the ledger can bring it back. */
export async function previewStopwordPurge(): Promise<StopwordPurgePreview> {
  return unwrap<StopwordPurgePreview>(await client.POST("/api/v1/taxonomy/tags/stopwords/purge/preview"));
}

/**
 * Deletes every tag whose name is a banned term, and logs each one in the ledger first.
 *
 * Sent with an empty body on purpose: registering words in the same call would make the numbers the
 * archivist approved different from the numbers that die. The response carries the ``purge_ids`` the
 * screen needs to offer the undo.
 */
export async function purgeStopwords(): Promise<StopwordPurgeResponse> {
  return unwrap<StopwordPurgeResponse>(
    await client.POST("/api/v1/taxonomy/tags/stopwords/purge", { body: {} }),
  );
}

/** The audit trail of the purges: what died, by whom, and what was restored. */
export async function fetchStopwordPurgeLog(params?: {
  includeUndone?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<StopwordPurgeLogListResponse> {
  return unwrap<StopwordPurgeLogListResponse>(
    await client.GET("/api/v1/taxonomy/tags/stopwords/purge-log", {
      params: {
        query: {
          include_undone: params?.includeUndone,
          q: params?.q,
          limit: params?.limit,
          offset: params?.offset,
        },
      },
    }),
  );
}

/** Undoes one purge from the ledger: the tag, its links and its spellings come back. */
export async function undoStopwordPurge(purgeId: number): Promise<StopwordPurgeUndoResponse> {
  return unwrap<StopwordPurgeUndoResponse>(
    await client.DELETE("/api/v1/taxonomy/tags/stopwords/purge-log/{purge_id}", {
      params: { path: { purge_id: purgeId } },
    }),
  );
}

// --- The subject axis, second half: the terms that are not a subject at all --------------------

/** The curated half of ``NENHUMA``: terms no rule catches because the call is semantic. */
export async function fetchSubjectExclusions(): Promise<string[]> {
  return unwrap<string[]>(await client.GET("/api/v1/taxonomy/tags/subject-exclusions"));
}

/**
 * The deterministic guard's own refusals, computed — and the evidence beside each one.
 *
 * Deliberately not a model: the guard is a pure function of the spelling, so its verdict cannot
 * hallucinate and costs no inference. What the route adds is visibility — the guard has been
 * skipping these terms inside the classifier while ``source='RULE'`` sat unused in the schema.
 */
export async function fetchSubjectExclusionSuggestions(
  params: NonNullable<
    paths["/api/v1/taxonomy/tags/subject-exclusions/suggestions"]["get"]["parameters"]["query"]
  > = {},
): Promise<SubjectExclusionSuggestionResponse> {
  return unwrap<SubjectExclusionSuggestionResponse>(
    await client.GET("/api/v1/taxonomy/tags/subject-exclusions/suggestions", { params: { query: params } }),
  );
}

/**
 * What confirming these terms would do, before anything is written (#175).
 *
 * The plan is the write's own — ``plan_subject_exclusions`` is what the write consumes — so the
 * screen can name the drawer that already claims a term instead of learning it from the answer.
 */
export async function previewSubjectExclusions(body: SubjectExclusionPreviewRequest): Promise<SubjectExclusionPlan> {
  return unwrap<SubjectExclusionPlan>(
    await client.POST("/api/v1/taxonomy/tags/subject-exclusions/preview", { body }),
  );
}

/**
 * The subject-exclusion body, with ``source`` required.
 *
 * The model defaults it to ``HUMAN``, so omitting it is legal — and that is exactly why this client
 * asks: a verdict the guard produced (``RULE``) silently recorded as a human judgement is the one
 * lie the ledger cannot recover from. Everything else derives untouched.
 */
type SubjectExclusionBody = Omit<SubjectExclusionRequest, "source"> &
  Required<Pick<SubjectExclusionRequest, "source">>;

/**
 * Records the decision. ``source`` tells a shape from a judgement: ``RULE`` for a term the guard
 * refused and the archivist confirmed, ``HUMAN`` for one they typed.
 *
 * One statement in two halves: the classifier stops guessing at the term **and** its spelling is
 * banned from becoming a tag again, so the next ingestion does not recreate it. A term whose tag is
 * in a drawer is refused and reported in ``blocked`` — the answer says what it wrote and what it
 * would not.
 */
export async function excludeFromSubjects(body: SubjectExclusionBody): Promise<SubjectExclusionBanResponse> {
  return unwrap<SubjectExclusionBanResponse>(
    await client.POST("/api/v1/taxonomy/tags/subject-exclusions", { body }),
  );
}

export async function restoreToSubjects(body: SubjectExclusionRemovalRequest): Promise<SubjectExclusionRemovalResponse> {
  return unwrap<SubjectExclusionRemovalResponse>(
    await client.DELETE("/api/v1/taxonomy/tags/subject-exclusions", { body }),
  );
}

/**
 * The macro-suggestion body the screen can offer today.
 *
 * ``columns_to_extract`` exists on the route — it chooses the AI text the clustering reads — and no
 * screen offers it yet, so exposing it here would advertise a knob nothing sets. It comes back with
 * the Discover screen's picker (#174).
 */
/**
 * The AI text columns the clustering can read, and the ones it reads when none is chosen.
 *
 * The picker on the Discover screen renders from this read, so the list cannot drift from the tuple
 * the route validates against (#174).
 */
export async function fetchClusteringColumns(): Promise<ClusteringColumnsResponse> {
  return unwrap<ClusteringColumnsResponse>(await client.GET("/api/v1/taxonomy/tags/suggest-macro/columns"));
}

/**
 * Agrupamentos the collection so a drawer the vocabulary lacks can be discovered.
 *
 * It drags the real clustering engine into the process, so it is a deliberate click and never a
 * page load. Below the engine's own floor it answers ``total_suggestions: 0`` with a message,
 * which is why the screen must render the message instead of an empty list.
 */
export async function suggestMacroCategories(body: SuggestMacroRequest): Promise<MacroCategoriesSuggestionResponse> {
  return unwrap<MacroCategoriesSuggestionResponse>(
    await client.POST("/api/v1/taxonomy/tags/suggest-macro", { body }),
  );
}

// --- The named entities: relevance, similarity, merge, reclassification and the vetoes ---------

export async function fetchEntityRelevance(
  params: NonNullable<paths["/api/v1/taxonomy/entities/relevance"]["get"]["parameters"]["query"]>,
): Promise<EntityRelevanceResponse> {
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
export async function fetchSimilarEntities(
  params: NonNullable<paths["/api/v1/taxonomy/entities/similar"]["get"]["parameters"]["query"]>,
): Promise<EntitySimilarityResponse> {
  return unwrap<EntitySimilarityResponse>(
    await client.GET("/api/v1/taxonomy/entities/similar", { params: { query: params } }),
  );
}

export async function mergeEntities(body: EntityMergeRequest): Promise<EntityMergeResponse> {
  return unwrap<EntityMergeResponse>(await client.POST("/api/v1/taxonomy/entities/merge", { body }));
}

/** The dry run of an entity merge, computed by the same planner the write executes. */
export async function previewEntityMerge(body: EntityMergePreviewRequest): Promise<EntityMergePreviewResponse> {
  return unwrap<EntityMergePreviewResponse>(
    await client.POST("/api/v1/taxonomy/entities/merge/preview", { body }),
  );
}

/**
 * The entity merge ledger, optionally filtered by a term.
 *
 * ``q`` is matched **server-side against both sides** of each entry — the absorbed and the canonical
 * name — because "where did this spelling go?" does not say which side it was on.
 */
export async function fetchEntityMergeLog(
  params: NonNullable<paths["/api/v1/taxonomy/entities/merge-log"]["get"]["parameters"]["query"]>,
): Promise<EntityMergeLogList> {
  return unwrap<EntityMergeLogList>(
    await client.GET("/api/v1/taxonomy/entities/merge-log", { params: { query: params } }),
  );
}

/** Reverses one absorbed entity: the row, its links, its spellings and the canonical name. */
export async function undoEntityMerge(mergeId: number): Promise<EntityMergeUndoResponse> {
  return unwrap<EntityMergeUndoResponse>(
    await client.DELETE("/api/v1/taxonomy/entities/merge-log/{merge_id}", {
      params: { path: { merge_id: mergeId } },
    }),
  );
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

/**
 * Renames one name. Its own operation, not a side effect of absorbing a twin.
 *
 * ``keep_old_synonym`` is the archivist's answer to "is this a typo or two spellings of one thing?",
 * and the response says whether the old spelling still resolves to the entity.
 */
export async function renameEntity(
  entityId: number,
  body: EntityRenameRequest,
): Promise<EntityRenameResponse> {
  return unwrap<EntityRenameResponse>(
    await client.PATCH("/api/v1/taxonomy/entities/{entity_id}", {
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

/**
 * Bans terms from NER. The ban **deletes nothing**: it only stops the extractor from creating them
 * from now on, and the `DELETE` on the same path re-opens the term.
 */
export async function banNerExclusions(body: NerExclusionRequest): Promise<NerExclusionBanResponse> {
  return unwrap<NerExclusionBanResponse>(
    await client.POST("/api/v1/taxonomy/entities/ner-exclusions", { body }),
  );
}

/**
 * Undoes the ban for the given terms.
 *
 * The ``DELETE`` declares its own removal model since #176 — removing a ban has no reason to
 * declare — so the body is the route's, with nothing narrowed away.
 */
export async function unbanNerExclusions(body: NerExclusionRemovalRequest): Promise<NerExclusionRemovalResponse> {
  return unwrap<NerExclusionRemovalResponse>(
    await client.DELETE("/api/v1/taxonomy/entities/ner-exclusions", { body }),
  );
}

/** The dry run of the purge: the entities already extracted from a banned spelling that would die. */
export async function previewNerPurge(): Promise<NerPurgePreview> {
  return unwrap<NerPurgePreview>(await client.POST("/api/v1/taxonomy/entities/ner-exclusions/purge/preview"));
}

/**
 * Deletes every entity extracted from a banned spelling, after logging each one in the ledger.
 *
 * No body: the screen applies the list the preview showed. The veto stays in place.
 */
export async function purgeNerExclusions(): Promise<NerPurgeResponse> {
  return unwrap<NerPurgeResponse>(await client.POST("/api/v1/taxonomy/entities/ner-exclusions/purge"));
}

/** The audit trail of the NER purges: what died, by whom, and what was restored. */
export async function fetchNerPurgeLog(params?: {
  includeUndone?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<NerPurgeLogListResponse> {
  return unwrap<NerPurgeLogListResponse>(
    await client.GET("/api/v1/taxonomy/entities/ner-exclusions/purge-log", {
      params: {
        query: {
          include_undone: params?.includeUndone,
          q: params?.q,
          limit: params?.limit,
          offset: params?.offset,
        },
      },
    }),
  );
}

export async function undoNerPurge(purgeId: number): Promise<NerPurgeUndoResponse> {
  return unwrap<NerPurgeUndoResponse>(
    await client.DELETE("/api/v1/taxonomy/entities/ner-exclusions/purge-log/{purge_id}", {
      params: { path: { purge_id: purgeId } },
    }),
  );
}

// --- The tag x entity collision ----------------------------------------------------------------

/**
 * The collisions that exist today, annotated with whatever has already been decided about each.
 *
 * ``pair_kind`` is the lever that makes the list usable: ``near_duplicate`` is the same word written
 * differently (a spelling question) and ``exact_name`` is the same spelling on both axes (a
 * structural question, and the one a batch can settle). ``entity_type`` narrows it to a category —
 * the same selection the batch writes — and ``all`` hides nothing.
 */
export async function fetchCrossDomainConflicts(
  params: NonNullable<paths["/api/v1/taxonomy/conflicts/cross-domain"]["get"]["parameters"]["query"]>,
): Promise<CrossDomainConflictPage> {
  return unwrap<CrossDomainConflictPage>(
    await client.GET("/api/v1/taxonomy/conflicts/cross-domain", { params: { query: params } }),
  );
}

/**
 * What the judge decided, read from the review queue and not from the live scan.
 *
 * This is the read that was missing: an auto-resolution deletes the losing row, so 84 of the 88 real
 * decisions cannot appear in a trigram join. Each row says whether its two sides still exist, which
 * is what separates history from work that is still pending.
 */
export async function fetchJudgedConflicts(
  params: NonNullable<paths["/api/v1/taxonomy/conflicts/judged"]["get"]["parameters"]["query"]> = {},
): Promise<JudgedConflictPage> {
  return unwrap<JudgedConflictPage>(
    await client.GET("/api/v1/taxonomy/conflicts/judged", { params: { query: params } }),
  );
}

/**
 * The dry run, and it answers **both** verdicts.
 *
 * "Which side should win?" is a question about the difference between them — how many links each
 * would create, which row each would delete, which ban each would plant — so asking one side at a
 * time would need two round trips to answer it. Nothing is written.
 */
export async function previewConflictResolution(body: ConflictPreviewRequest): Promise<ConflictResolutionPlan> {
  return unwrap<ConflictResolutionPlan>(
    await client.POST("/api/v1/taxonomy/conflicts/resolve/preview", { body }),
  );
}

/**
 * Decides which side owns the spelling, and the answer is written to a different place per side.
 *
 * Entity wins -> the tag's name is banned from the subject axis; tag wins -> the term is recorded as
 * a NER exclusion with the tag that justifies it. The screen must say which one it is doing. The
 * response carries the ``resolution_id`` the undo needs.
 */
export async function resolveConflict(body: ConflictResolutionRequest): Promise<ConflictResolutionResponse> {
  return unwrap<ConflictResolutionResponse>(await client.POST("/api/v1/taxonomy/conflicts/resolve", { body }));
}

/**
 * One categorical verdict over a whole selection — "a street is an entity" — in a single call.
 *
 * The unit of the decision is the selection (``pair_kind`` narrowed by ``entity_type``); the unit of
 * the write is still the pair, so every entry in ``applied`` carries its own ``resolution_id`` and
 * its own undo. ``skipped`` is work an earlier pair of the same batch already finished, and it is
 * never reported as a failure.
 */
export async function resolveConflictBatch(body: ConflictBatchRequest): Promise<ConflictBatchResponse> {
  return unwrap<ConflictBatchResponse>(await client.POST("/api/v1/taxonomy/conflicts/resolve/batch", { body }));
}

/** The ledger of the resolutions: what was written, by whom, and what was reversed. */
export async function fetchConflictResolutions(
  params: NonNullable<paths["/api/v1/taxonomy/conflicts/resolutions"]["get"]["parameters"]["query"]> = {},
): Promise<ConflictResolutionLogList> {
  return unwrap<ConflictResolutionLogList>(
    await client.GET("/api/v1/taxonomy/conflicts/resolutions", { params: { query: params } }),
  );
}

/**
 * Reverses one resolution: the deleted row, its links and the ban it planted.
 *
 * The second attempt answers 409 and an unknown id 404 — the ledger entry is never deleted, so
 * "resolved, then reversed" survives the reversal.
 */
export async function undoConflictResolution(resolutionId: number): Promise<{ message: string; data: ConflictResolutionLogEntry }> {
  return unwrap<{ message: string; data: ConflictResolutionLogEntry }>(
    await client.DELETE("/api/v1/taxonomy/conflicts/resolutions/{resolution_id}", {
      params: { path: { resolution_id: resolutionId } },
    }),
  );
}

// --- Quality of the input data: the repeated excerpts ------------------------------------------

export async function fetchTextTemplates(
  params: NonNullable<paths["/api/v1/quality/text-templates"]["get"]["parameters"]["query"]>,
): Promise<TextTemplate[]> {
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
export async function suggestTextTemplates(
  body: SuggestTextTemplatesRequest,
): Promise<TemplateSuggestionResponse> {
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

/** The catalogue. ``includeInactive`` is what lets the screen show the way back. */
export async function fetchCleaningRules(includeInactive = false): Promise<CleaningRule[]> {
  return unwrap<CleaningRule[]>(
    await client.GET("/api/v1/quality/cleaning-rules", {
      params: { query: { include_inactive: includeInactive } },
    }),
  );
}

/**
 * The engines and presets an `LLM_CHECK` rule can name, read from the title-quality registry.
 *
 * The form used to be free text with a placeholder naming an engine that does not exist; this is
 * what replaces it, so the only names a person can pick are the ones the write accepts (#124).
 */
export async function fetchCleaningRuleEngines(): Promise<CleaningRuleEngine[]> {
  return unwrap<CleaningRuleEngine[]>(await client.GET("/api/v1/quality/cleaning-rules/engines"));
}

export async function createCleaningRule(
  body: CreateCleaningRuleRequest,
): Promise<CleaningRuleMutationResponse> {  return unwrap<CleaningRuleMutationResponse>(
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

/** The way back: the rule returns to the queue the worker reads, with its id and history intact. */
export async function activateCleaningRule(ruleId: number): Promise<CleaningRuleMutationResponse> {
  return unwrap<CleaningRuleMutationResponse>(
    await client.PATCH("/api/v1/quality/cleaning-rules/{rule_id}/activate", {
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
export async function fetchHierarchyTree(
  params: NonNullable<paths["/api/v1/hierarchy/tree"]["get"]["parameters"]["query"]>,
): Promise<HierarchyTree> {
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

/**
 * Declares an arrangement node the source never delivered.
 *
 * A fund, a section or a series with no documents yet has no reference code to be sliced out of:
 * the plan only decides the rungs the slicer proposed. This is the write that declares one by hand,
 * and the ladder is validated against the chosen parent by the same code a move uses.
 */
export async function createHierarchyNode(body: HierarchyNodeCreateRequest): Promise<HierarchyNodeSummary> {
  return unwrap<HierarchyNodeSummary>(await client.POST("/api/v1/hierarchy/nodes", { body }));
}

// --- The operations panel: read the workers, configure them, run them ---------------------------

/**
 * The whole panel in one request: nine workers with configuration, queues and last run.
 *
 * One request because the API serves it as one; splitting it here would make the screen show
 * numbers from different moments.
 */
export async function fetchSystemWorkers(): Promise<SystemWorkers> {
  return unwrap<SystemWorkers>(await client.GET("/api/v1/system/workers"));
}

/**
 * The persisted defaults of every worker — the configuration screen's own read.
 *
 * Apart from ``fetchSystemWorkers`` on purpose: that one carries the nine queue counts, and the
 * configuration screen shows none of them.
 */
export async function fetchSystemWorkerSettings(): Promise<SystemWorkerSettings> {
  return unwrap<SystemWorkerSettings>(await client.GET("/api/v1/system/workers/settings"));
}

/** The execution ledger, newest first; the filters are applied server-side. */
export async function fetchSystemRuns(
  params: NonNullable<paths["/api/v1/system/runs"]["get"]["parameters"]["query"]>,
): Promise<WorkerRunList> {
  return unwrap<WorkerRunList>(await client.GET("/api/v1/system/runs", { params: { query: params } }));
}

/**
 * What is breaking, grouped by root cause across the executions ledger and the API's own.
 *
 * The grouping key is computed by the database from the error text, so this is one row per cause and
 * not one per execution — which is the whole point of the screen.
 */
export async function fetchSystemFailures(
  params: NonNullable<paths["/api/v1/system/failures"]["get"]["parameters"]["query"]>,
): Promise<FailureGroupList> {
  return unwrap<FailureGroupList>(await client.GET("/api/v1/system/failures", { params: { query: params } }));
}

/**
 * Queues one run and answers immediately with the row it created.
 *
 * The body carries overrides for this run only. A worker that already has a run in flight answers
 * 409 — the guarantee is the partial unique index in the database, not a check the screen could do.
 */
export async function triggerWorkerRun(worker: string, body: WorkerRunRequest): Promise<WorkerRun> {
  return unwrap<WorkerRun>(
    await client.POST("/api/v1/system/workers/{worker_name}/runs", {
      params: { path: { worker_name: worker } },
      body,
    }),
  );
}

/** Persists the default engine/preset/batch/options of one worker. */
export async function saveWorkerSettings(
  worker: string,
  body: WorkerSettingsRequest,
): Promise<WorkerSettings> {
  return unwrap<WorkerSettings>(
    await client.PUT("/api/v1/system/workers/{worker_name}/settings", {
      params: { path: { worker_name: worker } },
      body,
    }),
  );
}

/**
 * How many units a **proposed** configuration would leave in the worker's queue, without saving it.
 *
 * The queue is keyed on the producer identity, so trying another engine, preset or threshold
 * re-reads units; the screen asks this before the write, and the body is the settings body so the
 * preview and the save cannot disagree about what was proposed.
 */
export async function previewWorkerQueue(
  worker: string,
  body: WorkerSettingsRequest,
): Promise<WorkerQueuePreview> {
  return unwrap<WorkerQueuePreview>(
    await client.POST("/api/v1/system/workers/{worker_name}/queue/preview", {
      params: { path: { worker_name: worker } },
      body,
    }),
  );
}

/** Drops the override so the worker follows the code again; idempotent. */
export async function clearWorkerSettings(worker: string): Promise<WorkerSettings> {
  return unwrap<WorkerSettings>(
    await client.DELETE("/api/v1/system/workers/{worker_name}/settings", {
      params: { path: { worker_name: worker } },
    }),
  );
}

/** The worker's agenda, or ``null`` when it has none (ADR 0015). */
export async function fetchSystemSchedule(worker: string): Promise<WorkerSchedule | null> {
  return unwrap<WorkerSchedule | null>(
    await client.GET("/api/v1/system/workers/{worker_name}/schedule", {
      params: { path: { worker_name: worker } },
    }),
  );
}

/** Creates or replaces the worker's agenda: the cron, the zone and the pinned request. */
export async function saveWorkerSchedule(
  worker: string,
  body: WorkerScheduleRequest,
): Promise<WorkerSchedule> {
  return unwrap<WorkerSchedule>(
    await client.PUT("/api/v1/system/workers/{worker_name}/schedule", {
      params: { path: { worker_name: worker } },
      body,
    }),
  );
}

/** Removes the agenda; the runs it already created stay in the ledger. */
export async function clearWorkerSchedule(worker: string): Promise<void> {
  return unwrap<void>(
    await client.DELETE("/api/v1/system/workers/{worker_name}/schedule", {
      params: { path: { worker_name: worker } },
    }),
  );
}

/** Who changed what, when — the audit trail of the worker's configuration. */
export async function fetchWorkerSettingsRevisions(params: {
  worker: string;
  limit?: number;
  offset?: number;
}): Promise<WorkerSettingsRevisionList> {
  return unwrap<WorkerSettingsRevisionList>(
    await client.GET("/api/v1/system/workers/{worker_name}/settings/revisions", {
      params: {
        path: { worker_name: params.worker },
        query: { limit: params.limit, offset: params.offset },
      },
    }),
  );
}

/** Database, Ollama (with the models the presets need), object storage and the process. */
export async function fetchSystemHealth(): Promise<SystemHealth> {
  return unwrap<SystemHealth>(await client.GET("/api/v1/system/health"));
}

// --- The first run ------------------------------------------------------------------------------

/**
 * Whether this installation still has to be brought to life.
 *
 * Public, and answerable without a cookie: the shell has to decide which form to draw *before* it
 * can ask who the person is. The API says nothing else — an installation with no accounts has no
 * secret to protect (ADR 0011).
 */
export async function fetchSetupStatus(): Promise<SetupStatusResponse> {
  return unwrap<SetupStatusResponse>(await client.GET("/api/v1/setup/status"));
}

/**
 * Creates the installation's first administrator and signs them in.
 *
 * It answers the account exactly like ``login``, cookie included, and it answers 409 forever once
 * any account exists — so the only way to see this succeed is to be the first one there.
 */
export async function createFirstAdmin(email: string, name: string, password: string): Promise<AuthUser> {
  return unwrap<AuthUser>(
    await client.POST("/api/v1/setup/admin", { body: { email, name, password } }),
  );
}

// --- The session -------------------------------------------------------------------------------

/** The account behind the cookie, or a rejection the shell turns into the sign-in screen. */
export async function fetchCurrentUser(): Promise<AuthUser> {
  return unwrap<AuthUser>(await client.GET("/api/v1/auth/me"));
}

/**
 * Opens a session. The cookie is ``HttpOnly`` and first-party, so nothing here stores a token: the
 * browser keeps it and ``openapi-fetch`` sends it with every later request on its own.
 */
export async function login(email: string, password: string): Promise<AuthUser> {
  return unwrap<AuthUser>(await client.POST("/api/v1/auth/login", { body: { email, password } }));
}

/** Ends the session and clears the cookie. */
export async function logout(): Promise<RouteResponse> {
  return unwrap<RouteResponse>(await client.POST("/api/v1/auth/logout"));
}

/** Replaces the signed-in account's own password, proving the current one. */
export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<RouteResponse> {
  return unwrap<RouteResponse>(
    await client.POST("/api/v1/auth/password", {
      body: { current_password: currentPassword, new_password: newPassword },
    }),
  );
}

// --- The accounts of the installation (the ``Permission.ADMIN`` surface) ------------------------

/**
 * The accounts, typed from the contract.
 *
 * ``AuthSession`` is deliberately not the session the browser holds: the row identifies a sign-in by
 * ``session_id`` and carries what lets somebody recognise it (agent, address, when). There is no
 * token in it, so nothing here can be replayed.
 */
export type AuthSession = components["schemas"]["AuthSessionDTO"];
export type CreateUserRequest = components["schemas"]["CreateUserCommand"];
export type UpdateUserRequest = components["schemas"]["UpdateUserCommand"];
export type SetPasswordRequest = components["schemas"]["SetPasswordCommand"];

/** Every account, deactivated ones included: they are what explains why somebody cannot sign in. */
export async function fetchUsers(): Promise<AuthUser[]> {
  return unwrap<AuthUser[]>(await client.GET("/api/v1/users"));
}

/** Creates an account. The password is temporary: the account replaces it at the first sign-in. */
export async function createUser(body: CreateUserRequest): Promise<AuthUser> {
  return unwrap<AuthUser>(await client.POST("/api/v1/users", { body }));
}

/** Renames, re-roles or (de)activates an account. Deactivating ends its sessions immediately. */
export async function updateUser(userId: number, body: UpdateUserRequest): Promise<AuthUser> {
  return unwrap<AuthUser>(
    await client.PATCH("/api/v1/users/{user_id}", {
      params: { path: { user_id: userId } },
      body,
    }),
  );
}

/** An administrator sets a password without knowing the old one; every session of the account ends. */
export async function resetUserPassword(
  userId: number,
  body: SetPasswordRequest,
): Promise<RouteResponse> {
  return unwrap<RouteResponse>(
    await client.POST("/api/v1/users/{user_id}/password", {
      params: { path: { user_id: userId } },
      body,
    }),
  );
}

/** Where an account is signed in, with the session making *this* request marked. */
export async function fetchUserSessions(userId: number): Promise<AuthSession[]> {
  return unwrap<AuthSession[]>(
    await client.GET("/api/v1/users/{user_id}/sessions", {
      params: { path: { user_id: userId } },
    }),
  );
}

/** Ends one session of one account. */
export async function revokeUserSession(userId: number, sessionId: number): Promise<RouteResponse> {
  return unwrap<RouteResponse>(
    await client.DELETE("/api/v1/users/{user_id}/sessions/{session_id}", {
      params: { path: { user_id: userId, session_id: sessionId } },
    }),
  );
}

/** Ends every session of one account — the "sign out everywhere" of a lost laptop. */
export async function revokeUserSessions(userId: number): Promise<RouteResponse> {
  return unwrap<RouteResponse>(
    await client.DELETE("/api/v1/users/{user_id}/sessions", {
      params: { path: { user_id: userId } },
    }),
  );
}
