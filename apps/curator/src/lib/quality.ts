/**
 * Portuguese labels for the input-quality codes (Fase 3.5).
 *
 * The two vocabularies here are the ones whose difference is a decision, not a wording:
 * ``rule_kind`` separates cleaning from destroying, and the excerpt ``scope`` says which consumer
 * stops reading a repeated block. Embedding either as a bare string in a screen would hide that.
 */

import type { BadgeTone } from "@/lib/hierarchy";

export const RULE_KIND_LABEL: Record<string, string> = {
  REWRITE: "reescreve o texto",
  VALIDATE: "só sinaliza",
  LLM_CHECK: "consulta o modelo",
};

export const RULE_KIND_TONE: Record<string, BadgeTone> = {
  REWRITE: "warn",
  VALIDATE: "neutral",
  LLM_CHECK: "accent",
};

export const RULE_KIND_HINT: Record<string, string> = {
  REWRITE:
    "O worker substitui cada ocorrência pelo texto de substituição. É a única espécie de regra que mexe no acervo.",
  VALIDATE:
    "O worker não toca no texto: quando a expressão casa, o documento ganha uma anomalia com o motivo declarado.",
  LLM_CHECK:
    "Opt-in: um modelo de linguagem dá uma opinião sobre o título. Sem uma regra ativa deste tipo, nenhum engine é carregado.",
};

export const TARGET_COLUMN_LABEL: Record<string, string> = {
  original_title: "título original",
  scope_content: "conteúdo/escopo",
  admin_bio_history: "história administrativa",
  provenance: "proveniência",
  archivist_notes: "notas do arquivista",
};

export const TEMPLATE_STATUS_LABEL: Record<string, string> = {
  SUGGESTED: "sugerido",
  APPROVED: "aprovado",
  REJECTED: "rejeitado",
};

export const TEMPLATE_STATUS_TONE: Record<string, BadgeTone> = {
  SUGGESTED: "warn",
  APPROVED: "ok",
  REJECTED: "danger",
};

export const TEMPLATE_ACTION_LABEL: Record<string, string> = {
  IGNORE: "tirar do texto",
  REPLACE: "substituir",
};

export const TEMPLATE_SCOPE_LABEL: Record<string, string> = {
  EMBEDDING: "vetor",
  NER: "extração de nomes",
  TITLE: "título sugerido",
};

/**
 * ``scope`` is the decision that matters, and the measurement is why.
 *
 * Approving everything the machine suggested **worsened** the ranking (Hit@10 0.562 → 0.500): the
 * title prefix helped the derived title and hurt the vector. So a block is dropped from the
 * consumers it damages and kept where it helps, one scope at a time.
 */
export const TEMPLATE_SCOPE_HINT: Record<string, string> = {
  EMBEDDING: "O trecho sai do texto que vira vetor. Foi o maior ganho medido: 53% do acervo compartilhava o mesmo bloco.",
  NER: "O trecho sai do texto que o extrator e o classificador leem.",
  TITLE: "O trecho sai do título sugerido. O prefixo 'Registros Fotográficos -' ajuda aqui e prejudica o vetor — por isso os escopos são separados.",
};

export function labelOf(labels: Record<string, string>, code: string): string {
  return labels[code] ?? code;
}

/**
 * The reason codes the quality validator writes, in the archivist's language.
 *
 * The column mixes a stable code with an optional payload, and the facet bucket follows that: the
 * bare code for most reasons, and ``RULE_MATCH:<rule>`` for the one whose payload is a catalogue
 * entry. ``LLM_SUSPECT`` carries free text the model wrote about a single title, so its bucket is
 * the code — a sidebar over prose would be a long tail of options that never repeat.
 */
export const ANOMALY_REASON_LABEL: Record<string, string> = {
  MISSING_DATE: "sem data",
  FUTURE_DATE: "data no futuro",
  EMPTY_TITLE: "título vazio",
  ALL_CAPS_TITLE: "título em caixa alta",
  REPEATED_TITLE: "título repetido",
  TITLE_ONLY_TEMPLATE: "título só com trecho de origem",
  SCOPE_ONLY_BOILERPLATE: "âmbito só com boilerplate",
  NO_TAGS: "sem assuntos",
  NO_TYPOLOGY: "sem tipologia",
  NO_ENTITIES: "sem entidades nomeadas",
  RULE_MATCH: "regra do arquivista",
  LLM_SUSPECT: "suspeita do modelo",
};

export const ANOMALY_REASON_HINT: Record<string, string> = {
  RULE_MATCH:
    "Uma regra VALIDATE ou LLM_CHECK ativa casou. O nome da regra vem depois dos dois-pontos e é ele que o filtro usa.",
  LLM_SUSPECT:
    "O modelo achou o título suspeito. O texto que ele escreveu fica na ficha, não no filtro: uma faceta sobre a prosa dele seria uma cauda de opções que nunca se repetem.",
};

/**
 * The bucket key as the archivist reads it.
 *
 * ``RULE_MATCH:data fora do intervalo`` becomes "regra do arquivista: data fora do intervalo", and
 * the key itself is what the filter sends back — the facet's key and the query's value are the same
 * string by construction, on both sides.
 */
export function anomalyReasonLabel(key: string): string {
  const [code = key, ...rest] = key.split(":");
  const base = ANOMALY_REASON_LABEL[code] ?? code;
  return rest.length > 0 ? `${base}: ${rest.join(":")}` : base;
}

/** The code without its payload, for looking up the hint of a bucket key. */
export function anomalyReasonCode(key: string): string {
  return key.split(":")[0] ?? key;
}

/**
 * The shapes the deterministic guard recognises, and what each one means.
 *
 * These are the reason a term never reaches the subject classifier. The guard has been applying them
 * silently inside the worker; the catalogue now says which shape fired, because "não é assunto" with
 * no reason is indistinguishable from a mistake.
 */
export const SIGNAL_LABEL: Record<string, string> = {
  PLACEHOLDER: "placeholder",
  YEAR: "ano isolado",
  MEASURE: "número com unidade",
  STREET: "logradouro",
  PERSON: "nome de pessoa",
  RECORDED: "decisão registrada",
};

export const SIGNAL_HINT: Record<string, string> = {
  PLACEHOLDER: "O parser de origem grava este texto quando o dado não veio; não é sobre coisa nenhuma.",
  YEAR: "Um ano solto é uma data, não um assunto — e o modelo o classificava com 0,73 de confiança.",
  MEASURE: "Número com unidade é medida, não conceito.",
  STREET: "Logradouro é lugar: sai do assunto e a faceta Lugar o reivindica.",
  PERSON: "Nome de pessoa é produtor ou biografado, não assunto.",
  RECORDED: "Não tem forma reconhecível: alguém decidiu, e a decisão é o motivo.",
};
