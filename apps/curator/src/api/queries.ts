import { queryOptions } from "@tanstack/react-query";

import {
  fetchDiagnosticSummary,
  fetchDiagnostics,
  fetchDocument,
  fetchDocuments,
  fetchHierarchyPlans,
  fetchHierarchyVocabulary,
  fetchInbox,
  fetchLevels,
  fetchMacroCategories,
  fetchMaterialisationLog,
  fetchMergeLog,
  fetchMergeProposals,
  fetchRevisions,
  fetchSimilarTags,
  fetchStopwords,
  fetchTagRelevance,
  type DocumentSearch,
  type PlanStatus,
  type MergeReason,
  type ProposalStatus,
  type StopwordsScope,
} from "./client";

/** Page sizes: the plan catalogue is ~52 rungs, the diagnostic pages are read one at a time. */
export const PLANS_PAGE_SIZE = 200;
export const DIAGNOSTICS_PAGE_SIZE = 25;
/** The merge queue is hundreds of clusters, so it pages; the ledger shows the latest runs. */
export const PROPOSALS_PAGE_SIZE = 20;
export const MERGE_LOG_PAGE_SIZE = 20;

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

  materialisationLog: () =>
    queryOptions({
      queryKey: ["hierarchy", "materialisation", "log"],
      queryFn: () => fetchMaterialisationLog({ include_undone: true, limit: 10, offset: 0 }),
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

  mergeLog: (limit: number) =>
    queryOptions({
      queryKey: ["taxonomy", "merge-log", limit],
      queryFn: () => fetchMergeLog({ include_undone: true, limit, offset: 0 }),
      staleTime: 5_000,
    }),

  stopwords: (axis?: StopwordsScope) =>
    queryOptions({
      queryKey: ["taxonomy", "stopwords", axis ?? "ALL"],
      queryFn: () => fetchStopwords(axis),
      staleTime: 30_000,
    }),
};

