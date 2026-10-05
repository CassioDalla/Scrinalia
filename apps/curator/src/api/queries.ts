import { queryOptions } from "@tanstack/react-query";

import {
  fetchDocument,
  fetchDocuments,
  fetchInbox,
  fetchLevels,
  fetchRevisions,
  type DocumentSearch,
} from "./client";

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
};
