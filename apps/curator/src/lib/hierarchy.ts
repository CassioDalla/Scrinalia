/**
 * Portuguese labels for the codes the arrangement API speaks.
 *
 * Only the *text* lives here: the codes themselves always come from the API
 * (``GET /hierarchy/flags``), so a value added on the back-end shows up on screen as its raw code
 * instead of being silently dropped by a list hardcoded in the front (see AGENTS.md: code is
 * English, end-user-visible text is Portuguese).
 */

export type BadgeTone = "neutral" | "ok" | "warn" | "danger" | "accent";

export const PLAN_STATUS_LABEL: Record<string, string> = {
  SUGGESTED: "Sugerido",
  APPROVED: "Aprovado",
  REJECTED: "Rejeitado",
};

export const PLAN_STATUS_TONE: Record<string, BadgeTone> = {
  SUGGESTED: "warn",
  APPROVED: "ok",
  REJECTED: "danger",
};

/**
 * Labels for every flag a plan row can carry.
 *
 * The list is not the contract — ``GET /hierarchy/flags`` is — but a code with no label here would
 * reach the archivist untranslated, so the four vocabularies are all covered: the proposal's, the
 * near-duplicate issue, the ladder violation and what the slicer noticed about the code.
 */
export const PLAN_FLAG_LABEL: Record<string, string> = {
  ORDINAL_INFERRED: "nível inferido",
  RECORD_WITHOUT_DOCUMENTS: "registro sem documentos",
  DUPLICATE_REFERENCE_CODE: "código duplicado",
  NEAR_DUPLICATE_NODE: "sósia de outro degrau",
  LEVEL_NOT_ALLOWED_AS_CHILD: "nível não cabe sob o pai",
  MID_CODE_IDENTIFIER: "identificador no meio do código",
  UNPARSED_TAIL: "final do código ilegível",
  NO_STRUCTURAL_TOKEN: "código sem vocabulário",
};

export const PLAN_FLAG_HINT: Record<string, string> = {
  ORDINAL_INFERRED:
    "O ordinal não veio de nenhum registro existente: é proposta, não declaração. Decida o nível olhando os níveis declarados abaixo.",
  RECORD_WITHOUT_DOCUMENTS:
    "Existe um registro com este código e nada pendurado nele. Adotá-lo preserva a identidade que já está no acervo.",
  DUPLICATE_REFERENCE_CODE:
    "Mais de um registro reivindica este código, então 'o' nó existente é ambíguo: decida qual deles é a unidade.",
  NEAR_DUPLICATE_NODE:
    "Um irmão difere por uma letra (FOTOGRAFIA x FOTOGRAFIAS). Nenhuma similaridade resolve isso: decida se este degrau existe ou se funde no outro.",
  LEVEL_NOT_ALLOWED_AS_CHILD:
    "O nível proposto não é posterior ao do pai na escada, então a materialização o recusaria. Funda num degrau existente ou escolha outro nível.",
  MID_CODE_IDENTIFIER:
    "Há um identificador antes do último token de vocabulário: a segmentação do código é um palpite.",
  UNPARSED_TAIL:
    "O final do código não é número puro (ex.: '(1)', '369B'). O código é listado, nunca adivinhado.",
  NO_STRUCTURAL_TOKEN: "O código não carrega vocabulário de arranjo nenhum: não há degrau a propor.",
};

/** Qual código de ação o materializador propõe para um degrau. */
export const ACTION_LABEL: Record<string, string> = {
  CREATE: "criar",
  ADOPT: "adotar",
  ALREADY: "já materializado",
};

export const ACTION_TONE: Record<string, BadgeTone> = {
  CREATE: "accent",
  ADOPT: "ok",
  ALREADY: "neutral",
};

export const ISSUE_LABEL: Record<string, string> = {
  ORPHAN: "Sem unidade superior",
  DOSSIER_WITHOUT_PARENT: "Dossiê na raiz",
  UNKNOWN_LEVEL: "Nível não classificado",
  PATH_DIVERGENCE: "Caminho divergente",
  LEVEL_DEPTH_MISMATCH: "Nível x profundidade do código",
};

export const ISSUE_HINT: Record<string, string> = {
  ORPHAN:
    "Descrição sem pai cujo nível exige uma unidade superior, mais as que não têm nível algum e por isso não podem ser julgadas. A correção é o arranjo ser materializado — ou este ramo não ter nenhum degrau aprovado.",
  DOSSIER_WITHOUT_PARENT:
    "O caso nomeado e mais estreito do anterior: um Dossiê (nível que exige pai) parado na raiz.",
  UNKNOWN_LEVEL:
    "A carga tolera nível desconhecido de propósito; o arquivista não. Corrija o nível no dossiê da descrição.",
  PATH_DIVERGENCE:
    "O caminho materializado não bate com o do pai. Deve ser sempre 0: só o serviço de mover escreve o caminho, e ele reescreve a subárvore inteira na mesma transação. Se aparecer, alguém escreveu por fora.",
  LEVEL_DEPTH_MISMATCH:
    "O nível declarado é minoria na profundidade do código. A norma é aprendida da coleção, não fixada no código: cinco tokens carregam Itens, uma Série e uma Seção ao mesmo tempo.",
};

/** Rótulos das chaves de ``HierarchyDiagnostic.detail``, que o diagnóstico monta por issue. */
export const DETAIL_LABEL: Record<string, string> = {
  code_depth: "profundidade do código",
  expected_ordinal: "ordinal esperado",
  declared_ordinal: "ordinal declarado",
  path: "caminho atual",
  expected_path: "caminho esperado",
};

/**
 * Where each problem is actually fixed.
 *
 * Every one of them is a link to a screen that exists: the diagnosis lists evidence and never
 * "corrects" anything by itself, so a problem whose fix is not implemented yet says so instead of
 * offering a button that would do nothing.
 */
export const ISSUE_ACTION: Record<string, { label: string; to: string; hint: string }> = {
  ORPHAN: {
    label: "ir para o plano de arranjo",
    to: "/arranjo/plano",
    hint: "O arranjo é materializado a partir dos degraus aprovados.",
  },
  DOSSIER_WITHOUT_PARENT: {
    label: "ir para o plano de arranjo",
    to: "/arranjo/plano",
    hint: "Um Dossiê exige uma unidade superior: aprove o degrau acima dele.",
  },
  UNKNOWN_LEVEL: {
    label: "corrigir no dossiê",
    to: "",
    hint: "Abra a descrição e escolha o nível de descrição na aba Arranjo.",
  },
  PATH_DIVERGENCE: {
    label: "corrigir no dossiê",
    to: "",
    hint: "O caminho só é reescrito pelo serviço de mover: confira a unidade superior da descrição.",
  },
  LEVEL_DEPTH_MISMATCH: {
    label: "corrigir no dossiê",
    to: "",
    hint: "Revise o nível declarado: ele é minoria naquela profundidade de código.",
  },
};


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
