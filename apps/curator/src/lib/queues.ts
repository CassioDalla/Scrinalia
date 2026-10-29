import { linkOptions } from "@tanstack/react-router";

import type { components } from "@/api/schema";
import { activeMessages } from "@/i18n/locale";
import type { Messages } from "@/i18n/pt";
import { SCREENS } from "@/lib/screens";

/** The stable identity of a home-screen queue, generated from the contract. */
export type QueueKey = components["schemas"]["QueueKey"];

type QueueCopy = {
  /** The card's title: the name of the queue. */
  label: string;
  /** One line under the count; it explains what the queue is, including when it is empty. */
  description: string;
};

/**
 * The copy of the home cards, keyed by the identity the API sends (ADR 0020 §5).
 *
 * A label is vocabulary, not a sentence: the API carries `key` and `count`, and the text lives
 * here, beside the rest of the interface's copy, where the copy pass and its gate can review it.
 * The `Record<QueueKey, QueueCopy>` is the gate — a queue added to the contract without an entry
 * here fails `tsc`, instead of rendering a blank card.
 */
export const QUEUE_COPY = new Proxy({} as Record<QueueKey, QueueCopy>, {
  get(_target, key) {
    return activeMessages().queues[key as QueueKey];
  },
});

/**
 * Where each home card leads, and with which filters (ADR 0021).
 *
 * This is the destination's **one** owner. The API carries the queue's identity and its count and
 * nothing else: a path is not copy, and a destination sent through the contract would make every
 * screen rename a contract change. The path is read from `lib/screens.ts` — the catalogue the
 * router is pinned to — and `linkOptions` validates the search against the screen that declares
 * it, so `aba=classificar&subject_state=…` is a typed object instead of a string split at runtime.
 *
 * `satisfies Record<QueueKey, …>` is the gate on the other side: a queue added to the contract
 * without a destination here fails `tsc`, and `test_curator_copy.py` checks the same pair from the
 * source text.
 */
export const QUEUE_DESTINATIONS = {
  hierarchy_orphans: linkOptions({ to: SCREENS.plan.path }),
  hierarchy_plans: linkOptions({ to: SCREENS.plan.path }),
  tag_merge_proposals: linkOptions({ to: SCREENS.tags.path }),
  cross_domain_conflicts: linkOptions({ to: SCREENS.conflicts.path }),
  subject_low_confidence: linkOptions({
    to: SCREENS.tags.path,
    search: { aba: "classificar", subject_state: "LOW_CONFIDENCE" },
  }),
  orphan_subject_tags: linkOptions({
    to: SCREENS.tags.path,
    search: { aba: "classificar", subject_state: "PENDING" },
  }),
  typology_low_confidence: linkOptions({ to: SCREENS.typologies.path }),
  anomalies: linkOptions({ to: SCREENS.anomalies.path }),
  unreviewed_documents: linkOptions({
    to: SCREENS.collection.path,
    search: { status: "PENDING_AI" },
  }),
} satisfies Record<QueueKey, unknown>;

// The catalogue is the definition; this fails `tsc` when the contract grows a queue the catalogue
// does not carry yet, which the old explicit Record did by construction.
type CatalogueIsExhaustive = QueueKey extends keyof Messages["queues"] ? true : never;
const _catalogueIsExhaustive: CatalogueIsExhaustive = true;
void _catalogueIsExhaustive;
