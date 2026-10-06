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
