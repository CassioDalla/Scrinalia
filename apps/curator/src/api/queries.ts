import { queryOptions } from "@tanstack/react-query";

import {
  fetchCleaningRules,
  fetchDeletions,
  fetchCrossDomainConflicts,
  fetchDiagnosticSummary,
  fetchDiagnostics,
  fetchDocument,
  fetchDocuments,
  fetchEntityRelevance,
  fetchHierarchyNode,
  fetchHierarchyPlans,
  fetchHierarchyTree,
  fetchHierarchyVocabulary,
  fetchInbox,
  fetchLevelCatalog,
  fetchLevels,
  fetchMacroCategories,
  fetchMaterialisationLog,
  fetchMergeLog,
  fetchMergeProposals,
  fetchNerExclusions,
  fetchRevisions,
  fetchSimilarEntities,
  fetchSimilarTags,
  fetchStopwords,
  fetchSubjectExclusions,
  fetchSystemHealth,
  fetchSystemRuns,
  fetchSystemWorkers,
  fetchTagRelevance,
  fetchTextTemplates,
  fetchWorkerSettingsRevisions,
  type DocumentSearch,
  type EntityType,
  type PlanStatus,
  type MergeReason,
  type ProposalStatus,
  type StopwordsScope,
  type TemplateStatus,
  type WorkerRunStatus,
} from "./client";

/** Page sizes: the plan catalogue is ~52 rungs, the diagnostic pages are read one at a time. */
export const PLANS_PAGE_SIZE = 200;
export const DIAGNOSTICS_PAGE_SIZE = 25;
/** The merge queue is hundreds of clusters, so it pages; the ledger shows the latest runs. */
export const PROPOSALS_PAGE_SIZE = 20;
export const MERGE_LOG_PAGE_SIZE = 20;
/** The tree is read one branch at a time, and a branch is small: 500 nodes covers the real roots. */
export const TREE_PAGE_SIZE = 500;
/** The entity and tag vocabularies are read by weight, so the head of the list is what matters. */
export const RELEVANCE_PAGE_SIZE = 50;
export const ANOMALIES_PAGE_SIZE = 20;
/** The execution ledger only grows, so it pages; the settings trail is short by nature. */
export const RUNS_PAGE_SIZE = 20;
export const SETTINGS_REVISIONS_PAGE_SIZE = 10;
/** The deletion ledger only grows, so it pages like the proposals queue. */
export const DELETIONS_PAGE_SIZE = 20;

/**
 * Server state, declared once per resource.
 *
 * ``staleTime`` is chosen per resource rather than globally, because the resources have genuinely
 * different lifetimes: the level catalogue changes when an archivist edits it (rarely), while the
 * work list is the thing the archivist is acting on and must not look stale after an action.
 */
export const queries = {
  inbox: () =>
    queryOptions({
      queryKey: ["curation", "inbox"],
      queryFn: fetchInbox,
      staleTime: 15_000,
    }),

  documents: (search: DocumentSearch) =>
    queryOptions({
      queryKey: ["documents", "search", search],
      queryFn: () => fetchDocuments(search),
      staleTime: 10_000,
      // Keeps the previous page on screen while the next one loads: paginating a table that blanks
      // out on every click is the classic way to make a list feel broken.
      placeholderData: (previous) => previous,
    }),

  document: (descriptionId: string) =>
    queryOptions({
      queryKey: ["documents", "detail", descriptionId],
      queryFn: () => fetchDocument(descriptionId),
      staleTime: 0,
    }),

  /**
   * The deletion ledger, one page at a time.
   *
   * Server-side search and paging, unlike the small in-memory ledgers: the trail has no ceiling, and a
   * filter that only saw the loaded page would answer "não está aqui" for a record that is.
   */
  deletions: (term: string | undefined, offset: number) =>
    queryOptions({
      queryKey: ["documents", "deletions", term ?? "", offset],
      queryFn: () => fetchDeletions({ term, limit: DELETIONS_PAGE_SIZE, offset }),
      staleTime: 15_000,
      placeholderData: (previous) => previous,
    }),

  revisions: (descriptionId: string) =>
    queryOptions({
      queryKey: ["documents", "revisions", descriptionId],
      queryFn: () => fetchRevisions(descriptionId),
      staleTime: 5_000,
    }),

  levels: () =>
    queryOptions({
      queryKey: ["hierarchy", "levels"],
      queryFn: fetchLevels,
      staleTime: 5 * 60_000,
    }),

  /**
   * The subject drawers, for the reclassification select of the dossier.
   *
   * Read once and kept: the vocabulary changes when a curator edits it, not while a document is
   * open. The retired drawers come too, which is deliberate — a tag may still sit in one, and the
   * select has to be able to show where it is.
   */
  macroCategories: () =>
    queryOptions({
      queryKey: ["taxonomy", "macro-categories"],
      queryFn: () => fetchMacroCategories(false),
      staleTime: 5 * 60_000,
    }),

  /**
   * The vocabularies the arrangement screens group by, read once and kept.
   *
   * They are a statement about the code, not about the collection, so they do not go stale while
   * the archivist works — which is exactly why the front must not carry its own copy.
   */
  hierarchyVocabulary: () =>
    queryOptions({
      queryKey: ["hierarchy", "vocabulary"],
      queryFn: fetchHierarchyVocabulary,
      staleTime: 5 * 60_000,
    }),

  /**
   * One page of rungs. The whole catalogue is small enough to be read at once, so the screen can
   * filter by flag and by code locally without a round trip per keystroke.
   */
  plans: (status: PlanStatus | undefined) =>
    queryOptions({
      queryKey: ["hierarchy", "plans", status ?? "ALL"],
      queryFn: () => fetchHierarchyPlans({ status, limit: PLANS_PAGE_SIZE, offset: 0 }),
      staleTime: 5_000,
      // A status tab that blanks the list while it loads reads as a broken screen.
      placeholderData: (previous) => previous,
    }),

  /**
   * The materialisation ledger.
   *
   * ``limit`` grows with "ver mais" and ``term`` is filtered on the server: the ledger has no ceiling,
   * and the search has to cover the whole trail, not the ten rows on screen.
   */
  materialisationLog: (limit: number, term: string | undefined) =>
    queryOptions({
      queryKey: ["hierarchy", "materialisation", "log", limit, term ?? ""],
      queryFn: () => fetchMaterialisationLog({ include_undone: true, q: term, limit, offset: 0 }),
      staleTime: 5_000,
    }),

  diagnosticSummary: () =>
    queryOptions({
      queryKey: ["hierarchy", "diagnostics", "summary"],
      queryFn: fetchDiagnosticSummary,
      staleTime: 15_000,
    }),

  diagnostics: (issue: string, offset: number) =>
    queryOptions({
      queryKey: ["hierarchy", "diagnostics", issue, offset],
      queryFn: () => fetchDiagnostics(issue, { limit: DIAGNOSTICS_PAGE_SIZE, offset }),
      staleTime: 10_000,
      placeholderData: (previous) => previous,
    }),

  // --- The subject vocabulary as a whole (wave 3) --------------------------------------------

  tagRelevance: (method: "count" | "tfidf", limit: number) =>
    queryOptions({
      queryKey: ["taxonomy", "tags", "relevance", method, limit],
      queryFn: () => fetchTagRelevance(method, limit),
      staleTime: 60_000,
    }),

  /** Every pair above the threshold: the evidence a merge proposal is built from. */
  similarTagPairs: (threshold: number) =>
    queryOptions({
      queryKey: ["taxonomy", "tags", "similar", threshold],
      queryFn: () => fetchSimilarTags({ threshold }),
      staleTime: 60_000,
    }),

  mergeProposals: (filters: {
    status?: ProposalStatus;
    reason?: MergeReason;
    min_documents?: number;
    flagged_only?: boolean;
    offset?: number;
  }) =>
    queryOptions({
      queryKey: ["taxonomy", "merge-proposals", filters],
      queryFn: () =>
        fetchMergeProposals({ ...filters, limit: PROPOSALS_PAGE_SIZE, offset: filters.offset ?? 0 }),
      staleTime: 10_000,
      placeholderData: (previous) => previous,
    }),

  /** The merge ledger: server-side term, growing window — same reasoning as the materialisation one. */
  mergeLog: (limit: number, term: string | undefined) =>
    queryOptions({
      queryKey: ["taxonomy", "merge-log", limit, term ?? ""],
      queryFn: () => fetchMergeLog({ include_undone: true, q: term, limit, offset: 0 }),
      staleTime: 5_000,
    }),

  stopwords: (axis?: StopwordsScope) =>
    queryOptions({
      queryKey: ["taxonomy", "stopwords", axis ?? "ALL"],
      queryFn: () => fetchStopwords(axis),
      staleTime: 30_000,
    }),

  /** The curated "this is not a subject" list. It is a bare list of normalized terms. */
  subjectExclusions: () =>
    queryOptions({
      queryKey: ["taxonomy", "subject-exclusions"],
      queryFn: fetchSubjectExclusions,
      staleTime: 30_000,
    }),

  // --- The named entities (wave 5) ------------------------------------------------------------

  /**
   * The entity vocabulary by weight.
   *
   * ``entity_type`` filters server-side: the three types answer different questions (a person is
   * not a place), so switching the tab is a new read and not a client-side filter over a page.
   */
  entityRelevance: (entityType: EntityType | undefined, limit: number) =>
    queryOptions({
      queryKey: ["taxonomy", "entities", "relevance", entityType ?? "ALL", limit],
      queryFn: () => fetchEntityRelevance({ entity_type: entityType, limit }),
      staleTime: 60_000,
    }),

  /**
   * Trigrams among the entities, or the neighbours of one name.
   *
   * The two modes answer different payloads and the screen renders them differently, so the target
   * is part of the key: a cached "all pairs" page must never be shown as a neighbour search.
   */
  similarEntities: (targetName: string | undefined, threshold: number) =>
    queryOptions({
      queryKey: ["taxonomy", "entities", "similar", targetName ?? "ALL", threshold],
      queryFn: () => fetchSimilarEntities({ target_name: targetName, threshold }),
      staleTime: 60_000,
    }),

  nerExclusions: () =>
    queryOptions({
      queryKey: ["taxonomy", "ner-exclusions"],
      queryFn: fetchNerExclusions,
      staleTime: 30_000,
    }),

  crossDomainConflicts: (threshold: number) =>
    queryOptions({
      queryKey: ["taxonomy", "conflicts", threshold],
      // The trigram join is measured in seconds on the real vocabulary, so a threshold change is a
      // deliberate read and the answer is kept while the archivist works through the queue.
      queryFn: () => fetchCrossDomainConflicts(threshold),
      staleTime: 60_000,
    }),

  // --- Quality of the input data (wave 5) -----------------------------------------------------

  textTemplates: (status: TemplateStatus | undefined) =>
    queryOptions({
      queryKey: ["quality", "text-templates", status ?? "ALL"],
      queryFn: () => fetchTextTemplates({ status }),
      staleTime: 15_000,
    }),

  cleaningRules: () =>
    queryOptions({
      queryKey: ["quality", "cleaning-rules"],
      queryFn: fetchCleaningRules,
      // The list is the whole catalogue and it changes only when an archivist writes to it, which
      // is exactly when the screen invalidates it.
      staleTime: 60_000,
    }),

  // --- The arrangement: the ladder and the tree (wave 4) --------------------------------------

  /**
   * Every rung, retired ones included.
   *
   * The dossier's select reads only the active ones; this screen needs the retired ones too,
   * because the FK is ``SET NULL`` and a deactivated rung still holds the descriptions that sit on
   * it. Hiding them would make the weight of the ladder look smaller than it is.
   */
  levelCatalog: () =>
    queryOptions({
      queryKey: ["hierarchy", "levels", "catalog"],
      queryFn: fetchLevelCatalog,
      staleTime: 60_000,
    }),

  /**
   * One subtree of the materialised arrangement, flat and ordered by path.
   *
   * ``rootId`` is the branch the archivist opened and ``maxDepth`` how far below it to look, so the
   * navigation is one indexed read per level of interest instead of loading the collection.
   */
  tree: (rootId: string | undefined, maxDepth: number) =>
    queryOptions({
      queryKey: ["hierarchy", "tree", rootId ?? "ROOT", maxDepth],
      queryFn: () =>
        fetchHierarchyTree({ root_id: rootId, max_depth: maxDepth, limit: TREE_PAGE_SIZE }),
      // The tree only changes through the materialisation ledger, which the screen invalidates.
      staleTime: 30_000,
    }),

  node: (descriptionId: string) =>
    queryOptions({
      queryKey: ["hierarchy", "node", descriptionId],
      queryFn: () => fetchHierarchyNode(descriptionId),
      staleTime: 5_000,
    }),

  // --- The curator's work list over the collection (anomalies) --------------------------------

  /**
   * The documents the quality validator flagged, read through the same search the list uses.
   *
   * ``NEEDS_REVIEW`` is the status the validator writes, so this is a view of an existing
   * predicate — there is no anomaly route, and there should not be one.
   */
  anomalies: (offset: number) =>
    queryOptions({
      queryKey: ["quality", "anomalies", offset],
      queryFn: () =>
        fetchDocuments({ status: "NEEDS_REVIEW", limit: ANOMALIES_PAGE_SIZE, offset }),
      staleTime: 15_000,
      placeholderData: (previous) => previous,
    }),

  // --- The operations panel: the workers, the ledger and the probes ---------------------------

  /**
   * The catalogue, the effective configuration and the queues, in one request.
   *
   * The counts are live but not free — the transfer's counter validates the whole staging table —
   * so the screen keeps them for 30 s and only shortens that while a run is in flight.
   */
  systemWorkers: () =>
    queryOptions({
      queryKey: ["system", "workers"],
      queryFn: fetchSystemWorkers,
      staleTime: 30_000,
    }),

  /** The execution ledger, one page at a time; the filters are server-side like the collection's. */
  systemRuns: (worker: string | undefined, status: WorkerRunStatus | undefined, offset: number) =>
    queryOptions({
      queryKey: ["system", "runs", worker ?? "", status ?? "", offset],
      queryFn: () => fetchSystemRuns({ worker, status, limit: RUNS_PAGE_SIZE, offset }),
      staleTime: 10_000,
      placeholderData: (previous) => previous,
    }),

  /**
   * The infrastructure probes. Read on demand and kept for 30 s: the Ollama and S3 calls are
   * network I/O with a two-second ceiling each, so they are not something to refetch on every focus.
   */
  systemHealth: () =>
    queryOptions({
      queryKey: ["system", "health"],
      queryFn: fetchSystemHealth,
      staleTime: 30_000,
    }),

  /** The audit trail of one worker's configuration, shown next to the editor. */
  systemSettingsRevisions: (worker: string) =>
    queryOptions({
      queryKey: ["system", "settings", "revisions", worker],
      queryFn: () =>
        fetchWorkerSettingsRevisions({ worker, limit: SETTINGS_REVISIONS_PAGE_SIZE }),
      staleTime: 5_000,
    }),
};

