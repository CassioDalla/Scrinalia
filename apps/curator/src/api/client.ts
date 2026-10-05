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
