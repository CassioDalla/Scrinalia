/**
 * Portuguese labels for the tag-catalog codes.
 *
 * The codes themselves are the contract's (``MERGE_REASONS``, ``REVIEW_*``); only the text lives
 * here, like everywhere else in the front (see AGENTS.md: code is English, end-user-visible text is
 * Portuguese).
 */

import type { AccessPointPreviewItem } from "@/api/client";
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
    "A semelhança de algum membro com a canônica é baixa; o agrupamento pode estar juntando coisas diferentes.",
  CATEGORY_WOULD_BE_LOST:
    "Um dos membros está numa categoria de assunto que a canônica não tem. Mesclar exclui essa classificação.",
  MEMBER_IS_SYNONYM:
    "Algum membro é uma grafia que já foi absorvida por uma mesclagem anterior — o agrupamento pode ser reflexo de uma decisão antiga.",
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
  ENTITY: "entidades nomeadas",
  ALL: "os dois eixos",
};

export const STOPWORD_SCOPE_HINT: Record<string, string> = {
  TAG: "O termo sai do eixo de assunto. A exclusão das tags com esse nome guarda cada uma no registro, com desfazer.",
  ENTITY: "O termo sai da extração de nomes próprios. Não afeta tag nenhuma.",
  ALL: "O termo sai dos dois eixos, e a exclusão das tags o alcança.",
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
    "Bloqueia a palavra e qualquer nome que a contenha como palavra inteira — é o que pega o nome que o extrator devolve junto com ela (IPTU do Exemplo).",
  EXACT:
    "Bloqueia só a palavra inteira. Um nome que apenas começa ou contém a palavra passa: alameda sozinho é ruído, Alameda Cabral é uma rua.",
};

/**
 * Who planted a ban.
 *
 * The column exists because the purge preview has to tell a term banned **with the archive in mind**
 * from one typed by hand: ``CONFLICT`` came from settling a tag × entity collision and ``EXCLUSION``
 * from declaring the term not-a-subject — both are consequences of another decision — while
 * ``HUMAN`` is an act taken on the blocked-spellings screen.
 */
export const STOPWORD_SOURCE_LABEL: Record<string, string> = {
  HUMAN: "digitado aqui",
  CONFLICT: "veio de um conflito tag × entidade",
  EXCLUSION: "veio de “não é assunto”",
};

export const STOPWORD_SOURCE_HINT: Record<string, string> = {
  HUMAN: "Alguém digitou esta grafia em Grafias bloqueadas: é um ato deliberado.",
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
  ALL: "Lista completa de termos, ordenados por frequência de uso.",
  PENDING: "Termos pendentes de avaliação manual e automática.",
  NOT_SUBJECT:
    "Termo marcado manualmente como não sendo assunto. O termo fica bloqueado para novas etiquetas, mas as ocorrências atuais continuam no acervo e localizáveis na busca.",
  LOW_CONFIDENCE:
    "Classificação automática inconclusiva. A etiqueta aguarda validação humana, com a pontuação sugerida pelo sistema exibida na linha.",
};

/**
 * The four groups the creation form's access-point summary reads.
 *
 * The server answers one status per entry; the summary only has something to say about the
 * spellings the transfer will create, the ones it will drop, the ones it will map to a synonym, and
 * an existing tag whose stored spelling differs from what was typed. An exact existing tag is the
 * common case and produces no line at all.
 */
export type AccessPointPreviewGroups = {
  created: AccessPointPreviewItem[];
  dropped: AccessPointPreviewItem[];
  synonyms: AccessPointPreviewItem[];
  respelled: AccessPointPreviewItem[];
};

export function groupAccessPointPreview(items: AccessPointPreviewItem[]): AccessPointPreviewGroups {
  return {
    created: items.filter((item) => item.status === "NEW"),
    dropped: items.filter(
      (item) => item.status === "STOPWORD" || item.status === "TOO_SHORT" || item.status === "TOO_LONG",
    ),
    synonyms: items.filter((item) => item.status === "SYNONYM"),
    respelled: items.filter((item) => item.status === "EXISTING" && item.name !== null && item.name !== item.input),
  };
}

