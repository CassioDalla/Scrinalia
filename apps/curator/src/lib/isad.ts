import type { DocumentSummary, DocumentUpdateRequest } from "@/api/client";
import { activeMessages } from "@/i18n/locale";
import type { Messages } from "@/i18n/pt";

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

const AREA_IDS: readonly IsadAreaId[] = [
  "identity",
  "context",
  "content",
  "access",
  "allied",
  "notes",
  "control",
];

/** The area's copy, read when the screen renders so a language change re-renders it. */
function area(id: IsadAreaId): IsadArea {
  return {
    id,
    get title() {
      return activeMessages().isad.areas[id].title;
    },
    get hint() {
      return activeMessages().isad.areas[id].hint;
    },
  };
}

export const ISAD_AREAS: readonly IsadArea[] = AREA_IDS.map(area);

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

/** One field's metadata; the label and the help are the catalogue's, read at render time. */
type IsadFieldName = keyof Messages["isad"]["fields"];

function field(name: IsadFieldName, area: IsadAreaId, control: IsadControl, manualEntry = true): IsadField {
  return {
    name,
    area,
    control,
    manualEntry,
    get label() {
      return activeMessages().isad.fields[name].label;
    },
    get help() {
      return activeMessages().isad.fields[name].help;
    },
  };
}

export const ISAD_FIELDS: readonly IsadField[] = [
  field("reference_code", "identity", "text"),
  field("document_date", "identity", "date"),
  field("dimension_support", "identity", "text"),
  field("producers", "context", "entity"),
  field("admin_bio_history", "context", "long_text"),
  field("admin_archival_history", "context", "long_text"),
  field("provenance", "context", "long_text"),
  field("scope_content", "content", "long_text"),
  field("appraisal_destruction", "content", "long_text"),
  field("accruals", "content", "text"),
  field("arrangement", "content", "long_text"),
  field("access_conditions", "access", "long_text"),
  field("reproduction_conditions", "access", "long_text"),
  field("language_name", "access", "language"),
  field("physical_characteristics", "access", "long_text"),
  field("finding_aids", "access", "long_text"),
  field("originals_location", "allied", "text"),
  field("copies_location", "allied", "text"),
  field("related_units", "allied", "text"),
  field("publication_notes", "allied", "long_text"),
  field("general_notes", "notes", "long_text"),
  field("conservation_notes", "notes", "long_text"),
  field("archivist_notes", "control", "long_text"),
  field("rules_conventions", "control", "text"),
  field("description_dates", "control", "text", false),
];

/** The fields of one area, in the order they are typed. */
export function fieldsOfArea(area: IsadAreaId): readonly IsadField[] {
  return ISAD_FIELDS.filter((field) => field.area === area);
}
