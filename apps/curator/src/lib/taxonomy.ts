/**
 * Portuguese labels for the tag-catalog codes.
 *
 * The codes themselves are the contract's (``MERGE_REASONS``, ``REVIEW_*``); only the text lives
 * here, like everywhere else in the front (see AGENTS.md: code is English, end-user-visible text is
 * Portuguese).
 */

import type { BadgeTone } from "@/lib/hierarchy";

export const MERGE_REASON_LABEL: Record<string, string> = {
  TRIGRAM: "grafia parecida",
  PLURAL: "singular/plural",
  MIXED: "grafia e plural",
};

export const MERGE_REASON_TONE: Record<string, BadgeTone> = {
  TRIGRAM: "neutral",
  PLURAL: "accent",
  MIXED: "warn",
};

/**
 * The review flags are **warnings, not blocks** — the screen must not turn them into a refusal.
 *
 * The collection settled that: 58 agrupamentos carry ``MEMBER_WITH_DIGITS`` and both directions are real
 * (``br-116 ← br 116`` is right, ``rua ← rua 7`` is wrong). The archivist decides; the flag only says
 * where to look.
 */
export const REVIEW_FLAG_LABEL: Record<string, string> = {
  MEMBER_WITH_DIGITS: "membro com número",
  WEAK_MEMBER: "membro fraco",
  CATEGORY_WOULD_BE_LOST: "categoria seria perdida",
  MEMBER_IS_SYNONYM: "membro é grafia absorvida",
};

export const REVIEW_FLAG_HINT: Record<string, string> = {
  MEMBER_WITH_DIGITS:
    "Algum membro tem número no nome. Pode ser a mesma coisa (br-116 / br 116) ou outra (rua / rua 7): o número não decide.",
  WEAK_MEMBER:
    "A similaridade de algum membro com a canônica é baixa; o agrupamento pode estar juntando coisas diferentes.",
  CATEGORY_WOULD_BE_LOST:
    "Um dos membros está numa categoria de assunto que a canônica não tem. Mesclar exclui essa classificação.",
  MEMBER_IS_SYNONYM:
    "Algum membro é uma grafia que já foi absorvida por um merge anterior — o agrupamento pode ser reflexo de uma decisão antiga.",
};

export const PROPOSAL_STATUS_LABEL: Record<string, string> = {
  SUGGESTED: "sugerida",
  APPROVED: "aprovada",
  REJECTED: "rejeitada",
  // The write happened. Not a verdict the archivist has to revisit: a settled agrupamento.
  APPLIED: "aplicada",
};

export const PROPOSAL_STATUS_TONE: Record<string, BadgeTone> = {
  SUGGESTED: "warn",
  APPROVED: "ok",
  REJECTED: "danger",
  APPLIED: "neutral",
};

export function labelOf(labels: Record<string, string>, code: string): string {
  return labels[code] ?? code;
}

/**
 * The axis a banned term was taken out of.
 *
 * The distinction is not cosmetic and the screen has to say it: ``TAG`` (and ``ALL``) feed the
 * subject purge, which **deletes** the matching tags, while ``ENTITY`` only keeps the term out of
 * the NER extraction and never touches a tag. Reading an entity ban in the purge would delete a tag
 * the curator deliberately kept.
 */
export const STOPWORD_SCOPE_LABEL: Record<string, string> = {
  TAG: "assunto (tags)",
  ENTITY: "entidades (NER)",
  ALL: "os dois eixos",
};

export const STOPWORD_SCOPE_HINT: Record<string, string> = {
  TAG: "O termo sai do eixo de assunto. A purga exclui as tags com esse nome e guarda cada uma no ledger, com desfazer.",
  ENTITY: "O termo sai da extração de nomes próprios. Não afeta tag nenhuma.",
  ALL: "O termo sai dos dois eixos, e a purga o alcança.",
};

/**
 * How a ban on the extraction axis matches an extracted name (#160).
 *
 * Only ``TOKEN`` has to swallow the merged span the engine returns around a noise word
 * (``IPTU do Exemplo``); ``EXACT`` is what a generic word that also starts proper names needs
 * (``alameda`` alone, never ``Alameda Cabral``). The labels are the two behaviours, not the codes.
 */
export const STOPWORD_MATCH_LABEL: Record<string, string> = {
  TOKEN: "a palavra e os nomes que a contêm",
  EXACT: "só a grafia exata",
};

export const STOPWORD_MATCH_HINT: Record<string, string> = {
  TOKEN:
    "Bloqueia a palavra e qualquer nome que a contenha como palavra inteira — é o que pega o span fundido que o extrator devolve (IPTU do Exemplo).",
  EXACT:
    "Bloqueia só a palavra inteira. Um nome que apenas começa ou contém a palavra passa: alameda sozinho é ruído, Alameda Cabral é uma rua.",
};

/**
 * Who planted a ban.
 *
 * The column exists because the purge preview has to tell a term banned **with the archive in mind**
 * from one typed by hand: ``CONFLICT`` came from settling a tag × entity collision and ``EXCLUSION``
 * from declaring the term not-a-subject — both are consequences of another decision — while
 * ``HUMAN`` is an act taken on the Stopwords screen.
 */
export const STOPWORD_SOURCE_LABEL: Record<string, string> = {
  HUMAN: "digitado aqui",
  CONFLICT: "veio de um conflito tag × entidade",
  EXCLUSION: "veio de “não é assunto”",
};

export const STOPWORD_SOURCE_HINT: Record<string, string> = {
  HUMAN: "Alguém digitou este termo na aba Stopwords: é um ato deliberado.",
  CONFLICT: "O termo foi banido ao resolver um conflito entre a tag e a entidade de mesma grafia.",
  EXCLUSION:
    "O termo foi banido junto com a decisão “não é assunto”. O desfazer daquela decisão levanta este ban.",
};

/**
 * The state of a tag's subject decision, as the archivist reads it.
 *
 * The three states are a partition of the tags with no category (see
 * ``repository/subject_queue.py``), and the labels say which question each one answers. ``ALL`` is
 * not a state: it is the absence of a filter. A producer, a place or a person is **not** a fourth
 * state: the entity axis carries what it is, and the tag × entity conflict screen settles a spelling
 * that is both (ADR 0013).
 */
export const CATALOG_STATE_LABEL: Record<string, string> = {
  ALL: "Todas",
  PENDING: "Sem decisão",
  NOT_SUBJECT: "Não é assunto",
  LOW_CONFIDENCE: "Confiança baixa",
};

export const CATALOG_STATE_HINT: Record<string, string> = {
  ALL: "O catálogo inteiro, mais pesado primeiro.",
  PENDING: "Nenhuma pessoa decidiu ainda, e o classificador também não: é a fila que o Início conta.",
  NOT_SUBJECT:
    "Uma pessoa declarou que a tag não é assunto: o classificador para de adivinhar e a grafia não volta a virar tag. A tag atual fica no acervo, alcançável pela busca.",
  LOW_CONFIDENCE:
    "O classificador rodou e não teve confiança para arquivar a tag; ela continua sem decisão. A nota dele aparece na linha.",
};
