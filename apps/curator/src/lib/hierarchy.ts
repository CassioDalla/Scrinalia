/**
 * Portuguese labels for the codes the arrangement API speaks.
 *
 * Only the *text* lives here: the codes themselves always come from the API
 * (``GET /hierarchy/flags``), so a value added on the back-end shows up on screen as its raw code
 * instead of being silently dropped by a list hardcoded in the front (see AGENTS.md: code is
 * English, end-user-visible text is Portuguese).
 */

import { activeMessages } from "@/i18n/locale";
import type { Messages } from "@/i18n/pt";

export type BadgeTone = "neutral" | "ok" | "warn" | "danger" | "accent";

type Hierarchy = Messages["hierarchy"];

/** A section whose entries are plain strings, read when the screen renders. */
function stringMap<K extends keyof Hierarchy>(section: K): Record<string, string> {
  return new Proxy({} as Record<string, string>, {
    get(_target, key) {
      const entry = activeMessages().hierarchy[section] as Record<string, unknown>;
      const value = entry[String(key)];
      return typeof value === "string" ? value : String(key);
    },
  });
}

/** A section whose entries carry a label and a hint, read when the screen renders. */
function fieldMap<K extends keyof Hierarchy>(section: K, field: "label" | "hint"): Record<string, string> {
  return new Proxy({} as Record<string, string>, {
    get(_target, key) {
      const entry = (activeMessages().hierarchy[section] as Record<string, Record<string, string> | undefined>)[
        String(key)
      ];
      return entry?.[field] ?? (field === "label" ? String(key) : "");
    },
  });
}

export const PLAN_STATUS_LABEL = stringMap("planStatus");

export const PLAN_STATUS_TONE: Record<string, BadgeTone> = {
  SUGGESTED: "warn",
  APPROVED: "ok",
  REJECTED: "danger",
};

export const PLAN_FLAG_LABEL = fieldMap("planFlag", "label");
export const PLAN_FLAG_HINT = fieldMap("planFlag", "hint");

export const ACTION_LABEL = stringMap("planAction");

export const ACTION_TONE: Record<string, BadgeTone> = {
  CREATE: "accent",
  ADOPT: "ok",
  ALREADY: "neutral",
};

export const ISSUE_LABEL = fieldMap("issue", "label");
export const ISSUE_HINT = fieldMap("issue", "hint");

export const DETAIL_LABEL = stringMap("detail");

/**
 * Where each problem is actually fixed. The route is code; the words are the catalogue's, read at
 * render time so the link follows the interface's language.
 */
const ISSUE_ROUTES: Record<string, string> = {
  ORPHAN: "/arranjo/plano",
  DOSSIER_WITHOUT_PARENT: "/arranjo/plano",
  UNKNOWN_LEVEL: "",
  PATH_DIVERGENCE: "",
  LEVEL_DEPTH_MISMATCH: "",
};

export const ISSUE_ACTION = new Proxy({} as Record<string, { label: string; to: string; hint: string }>, {
  get(_target, key) {
    const code = String(key) as keyof Messages["hierarchy"]["issue"];
    return {
      to: ISSUE_ROUTES[code] ?? "",
      get label() {
        return activeMessages().hierarchy.issue[code].actionLabel;
      },
      get hint() {
        return activeMessages().hierarchy.issue[code].actionHint;
      },
    };
  },
});

export function labelOf(labels: Record<string, string>, code: string): string {
  return labels[code] ?? code;
}

/**
 * The placeholder the staging parser writes when the source carries no title.
 *
 * It is data, not an error — but a tree that repeats it six times says nothing at all, which is
 * exactly what the first render of ``/acervo/arvore`` did.
 */
export const UNTITLED = "SEM TÍTULO";

/**
 * What to call a node on screen.
 *
 * Falls back to the reference code and then to the identifier: those at least tell the archivist
 * *which* description they are looking at. The raw title stays available to the caller for a
 * tooltip, so nothing is hidden — it is just not repeated as a label.
 */
export function nodeLabel(node: {
  title?: string | null;
  reference_code?: string | null;
  description_id: string;
}): string {
  const title = node.title?.trim();
  if (title && title !== UNTITLED) return title;
  return node.reference_code?.trim() || node.description_id;
}
