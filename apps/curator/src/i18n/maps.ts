/**
 * Two small factories for copy that is a map keyed by an identity.
 *
 * The screens index these maps at render time (`MERGE_REASON_LABEL[code]`), so the catalogue is read
 * through a proxy instead of being copied at import: a language change re-renders the tree and the
 * words follow it. `fieldMap` is for entries that carry a label and a hint, the pair the vocabulary
 * screens show together.
 */

import { activeMessages } from "@/i18n/locale";
import type { Messages } from "@/i18n/pt";

type Strings = Record<string, unknown>;

/** A map whose values are strings. A missing key renders the raw code, never an empty cell. */
export function stringMap(select: (messages: Messages) => Strings): Record<string, string> {
  return new Proxy({} as Record<string, string>, {
    get(_target, key) {
      const value = select(activeMessages())[String(key)];
      return typeof value === "string" ? value : String(key);
    },
  });
}

/** A map whose entries are `{ label, hint }`. */
export function fieldMap(select: (messages: Messages) => Strings, field: "label" | "hint"): Record<string, string> {
  return new Proxy({} as Record<string, string>, {
    get(_target, key) {
      const entry = select(activeMessages())[String(key)] as Record<string, string> | undefined;
      return entry?.[field] ?? (field === "label" ? String(key) : "");
    },
  });
}

/** Fills the catalogue's `{name}` placeholders; the same convention the server's refusals use. */
export function fill(template: string, facts: Record<string, string | number>): string {
  return Object.entries(facts).reduce((text, [key, value]) => text.replace(`{${key}}`, String(value)), template);
}
