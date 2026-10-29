import type { components } from "@/api/schema";
import { activeMessages } from "@/i18n/locale";
import type { Messages } from "@/i18n/pt";

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
 * A label is vocabulary, not a sentence: the API carries `key`, `count` and `route`, and the text
 * lives here, beside the rest of the interface's copy, where the copy pass and its gate can review
 * it. The `Record<QueueKey, QueueCopy>` is the gate — a queue added to the contract without an
 * entry here fails `tsc`, instead of rendering a blank card.
 */
export const QUEUE_COPY = new Proxy({} as Record<QueueKey, QueueCopy>, {
  get(_target, key) {
    return activeMessages().queues[key as QueueKey];
  },
});

// The catalogue is the definition; this fails `tsc` when the contract grows a queue the catalogue
// does not carry yet, which the old explicit Record did by construction.
type CatalogueIsExhaustive = QueueKey extends keyof Messages["queues"] ? true : never;
const _catalogueIsExhaustive: CatalogueIsExhaustive = true;
void _catalogueIsExhaustive;
