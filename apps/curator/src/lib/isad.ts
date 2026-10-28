import type { DocumentSummary, DocumentUpdateRequest } from "@/api/client";

/**
 * The ISAD(G) record, area by area, named once.
 *
 * The dossier edits the record and the manual entry form creates one; both ask the same questions in
 * the same order, and the labels are the archivist's. Keeping the list here is what stops the two
 * screens from drifting into two vocabularies for one norm — and it is the list the "every field is
 * reachable" gate reads (a field added to the contract without a control here fails the suite).
 *
 * What is **not** here: the title and the level, which the dossier edits as its identity block and
 * the form sends at creation; the typology and the diffusion flag, which are the dossier's own
 * decisions; and the three fields the archive keeps as evidence rather than as an editable record —
 * ``date_expression`` (how the source spelled the date), ``original_url`` (where the record came
 * from) and ``parent_reference_code`` (the parent the origin declared, moved through the arrangement
 * tab, not typed).
 */

export type IsadAreaId = "identity" | "context" | "content" | "access" | "allied" | "notes" | "control";

export type IsadArea = {
  id: IsadAreaId;
  /** The norm's own number and name, so the archivist recognizes the area. */
  title: string;
  /** What the area is about, in one line: the form shows it under the heading. */
  hint: string;
};

export const ISAD_AREAS: readonly IsadArea[] = [
  {
    id: "identity",
    title: "3.1 Identidade",
    hint: "O que a descrição é: código, nível, datas e dimensão.",
  },
  {
    id: "context",
    title: "3.2 Contexto",
    hint: "Quem produziu, como o conjunto chegou até aqui e de onde o registro veio.",
  },
  {
    id: "content",
    title: "3.3 Conteúdo e Estrutura",
    hint: "O que o documento diz e como o conjunto está organizado.",
  },
  {
    id: "access",
    title: "3.4 Acesso e Uso",
    hint: "Quem pode consultar, como reproduzir e o que é preciso para usar o documento.",
  },
  {
    id: "allied",
    title: "3.5 Materiais Relacionados",
    hint: "Onde estão os originais e as cópias, e que outras descrições se relacionam com esta.",
  },
  {
    id: "notes",
    title: "3.6 Notas",
    hint: "Observações gerais e sobre o estado de conservação.",
  },
  {
    id: "control",
    title: "3.7 Controle da Descrição",
    hint: "Quem descreveu, sob que regras e quando.",
  },
];

/** The control a field needs. A screen that does not know the kind falls back to a text input. */
export type IsadControl = "text" | "long_text" | "date" | "language" | "entity";

export type IsadField = {
  /** The API's field name, spelled exactly as the contract spells it. */
  name: keyof DocumentUpdateRequest & keyof DocumentSummary;
  label: string;
  area: IsadAreaId;
  control: IsadControl;
  /** One line the form shows under the control: what to type, not what the field is. */
  help: string;
  /**
   * ``false`` when the manual entry form does not ask it.
   *
   * The dossier edits the description control area, but a record being born has no "date of the
   * description" to declare — the archive knows when it was made. Marking the omission here is what
   * keeps "every field has a control" a gate instead of a list of exceptions inside the test.
   */
  manualEntry?: boolean;
};

export const ISAD_FIELDS: readonly IsadField[] = [
  {
    name: "reference_code",
    label: "Código de Referência",
    area: "identity",
    control: "text",
    help: "O código que identifica a unidade de descrição no arranjo.",
  },
  {
    name: "document_date",
    label: "Data do Documento",
    area: "identity",
    control: "date",
    help: "AAAA-MM-DD, ou a expressão como está na fonte (Década de 1980, 1951-1953).",
  },
  {
    name: "dimension_support",
    label: "Dimensão e Suporte",
    area: "identity",
    control: "text",
    help: "Quantidade e o suporte do material. Ex: 2 folhas; 1 fotografia em papel; 3,5 m de documentos textuais.",
  },
  {
    name: "producers",
    label: "Produtor(es)",
    area: "context",
    control: "entity",
    help: "Quem produziu o conjunto: a instituição ou a pessoa. A lista sugere nomes das entidades; escolher um copia o nome, sem criar vínculo.",
  },
  {
    name: "admin_bio_history",
    label: "História Administrativa / Biografia",
    area: "context",
    control: "long_text",
    help: "A trajetória da entidade ou pessoa produtora para contextualizar a criação e o uso dos documentos.",
  },
  {
    name: "admin_archival_history",
    label: "História Arquivística",
    area: "context",
    control: "long_text",
    help: "Informações sobre a custódia, proveniência, acumulação, mudanças de propriedade ou alterações na organização do acervo ao longo do tempo.",
  },
  {
    name: "provenance",
    label: "Procedência",
    area: "context",
    control: "long_text",
    help: "Identificação da fonte imediata de aquisição ou transferência do acervo (doador, alienante, recolhedor ou custodiante anterior).",
  },
  {
    name: "scope_content",
    label: "Âmbito e Conteúdo",
    area: "content",
    control: "long_text",
    help: "Síntese do tema central, alcance temporal, funções/atividades representadas e principais entidades ou indivíduos mencionados no acervo.",
  },
  {
    name: "appraisal_destruction",
    label: "Avaliação e Temporalidade",
    area: "content",
    control: "long_text",
    help: "O prazo de guarda e a decisão de eliminação, quando houver.",
  },
  {
    name: "accruals",
    label: "Incorporações",
    area: "content",
    control: "text",
    help: "Indica se são esperados acréscimos ou novas entradas de documentos a esta unidade de descrição (acervo aberto ou fechado).",
  },
  {
    name: "arrangement",
    label: "Sistema de Arranjo",
    area: "content",
    control: "long_text",
    help: "Informações sobre a estrutura de organização, plano de classificação e critérios de ordenação interna da unidade de descrição.",
  },
  {
    name: "access_conditions",
    label: "Condições de Acesso",
    area: "access",
    control: "long_text",
    help: "Informações sobre o estatuto legal ou regulamentos que restringem ou autorizam a consulta pública à unidade de descrição.",
  },
  {
    name: "reproduction_conditions",
    label: "Condições de Reprodução",
    area: "access",
    control: "long_text",
    help: "Restrições relativas a direitos autorais, reprodução (cópias, fotografias) ou publicação dos documentos.",
  },
  {
    name: "language_name",
    label: "Idioma",
    area: "access",
    control: "language",
    help: "O idioma predominante do documento.",
  },
  {
    name: "physical_characteristics",
    label: "Características Físicas",
    area: "access",
    control: "long_text",
    help: "Informações sobre o estado de conservação, suporte físico e exigências técnicas ou de preservação para a consulta dos documentos.",
  },
  {
    name: "finding_aids",
    label: "Instrumentos de Pesquisa",
    area: "access",
    control: "long_text",
    help: "Referência a guias, inventários, repertórios ou bases de dados que facilitem a localização e o acesso à unidade de descrição.",
  },
  {
    name: "originals_location",
    label: "Existência e Localização dos Originais",
    area: "allied",
    control: "text",
    help: "Endereço ou instituição detentora da documentação original quando a unidade de descrição for constituída por cópias.",
  },
  {
    name: "copies_location",
    label: "Existência e Localização de Cópias",
    area: "allied",
    control: "text",
    help: "Informações sobre cópias em outros formatos ou suportes, bem como sua localização ou identificação no acervo.",
  },
  {
    name: "related_units",
    label: "Unidades de Descrição Relacionadas",
    area: "allied",
    control: "text",
    help: "Referências cruzadas a outras unidades de descrição com as quais este acervo guarda proveniência ou relação temática.",
  },
  {
    name: "publication_notes",
    label: "Notas de Publicação",
    area: "allied",
    control: "long_text",
    help: "Referências bibliográficas de publicações baseadas na pesquisa, uso ou reprodução da unidade de descrição.",
  },
  {
    name: "general_notes",
    label: "Notas Gerais",
    area: "notes",
    control: "long_text",
    help: "Informações adicionais que não puderam ser incluídas nos campos anteriores da descrição arquivística.",
  },
  {
    name: "conservation_notes",
    label: "Notas de Conservação",
    area: "notes",
    control: "long_text",
    help: "Registro de danos, condições de preservação e tratamentos conservativos ou restaurativos aplicados ou requeridos.",
  },
  {
    name: "archivist_notes",
    label: "Notas do Arquivista",
    area: "control",
    control: "long_text",
    help: "Anotações relativas ao trabalho do responsável pela descrição, procedimentos adotados e decisões arquivísticas.",
  },
  {
    name: "rules_conventions",
    label: "Regras ou Convenções",
    area: "control",
    control: "text",
    help: "Identificação dos padrões internacionais, nacionais ou institucionais utilizados na elaboração do registro.",
  },
  {
    name: "description_dates",
    label: "Datas da Descrição",
    area: "control",
    control: "text",
    help: "Registro cronológico da elaboração, revisão e atualizações da ficha arquivística.",
    // Not asked at creation: the record is being described now, and the archive knows when.
    manualEntry: false,
  },
];

/** The fields of one area, in the order they are typed. */
export function fieldsOfArea(area: IsadAreaId): readonly IsadField[] {
  return ISAD_FIELDS.filter((field) => field.area === area);
}
