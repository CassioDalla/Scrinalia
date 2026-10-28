import type { components } from "@/api/schema";

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
export const QUEUE_COPY: Record<QueueKey, QueueCopy> = {
  hierarchy_orphans: {
    label: "Arranjo não materializado",
    description: "Descrições que o arranjo ainda não consegue colocar numa cadeia.",
  },
  hierarchy_plans: {
    label: "Níveis aguardando decisão",
    description: "Níveis que a leitura dos códigos de referência propôs.",
  },
  tag_merge_proposals: {
    label: "Propostas de mesclagem de tags",
    description: "Tags com grafias parecidas que aguardam a decisão de mesclar.",
  },
  cross_domain_conflicts: {
    label: "Conflitos entre assunto e entidade",
    description: "Termos que colidem: o mesmo nome é assunto e nome próprio.",
  },
  subject_low_confidence: {
    label: "Assunto com confiança baixa",
    description: "Tags que o classificador não teve confiança para arquivar numa categoria.",
  },
  orphan_subject_tags: {
    label: "Tags sem categoria de assunto",
    description: "Tags sem categoria: nenhum selo de assunto pode ser mostrado para elas.",
  },
  typology_low_confidence: {
    label: "Tipologia com confiança baixa",
    description: "Descrições cuja tipologia o classificador não conseguiu decidir.",
  },
  anomalies: {
    label: "Anomalias detectadas",
    description: "Descrições que o validador de qualidade marcou.",
  },
  unreviewed_documents: {
    label: "Descrições não revisadas",
    description: "Descrições que nenhuma pessoa revisou ainda.",
  },
};
