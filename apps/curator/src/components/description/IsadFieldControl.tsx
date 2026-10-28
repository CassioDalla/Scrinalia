import type { Language } from "@/api/client";
import { Field } from "@/components/ui/Field";
import { Input, Select, Textarea } from "@/components/ui/Input";
import type { IsadField } from "@/lib/isad";

/**
 * One ISAD(G) control, rendered from the catalogue instead of from a list of labels.
 *
 * The dossier and the manual entry form ask the same questions and must not grow two widgets for
 * them: the field, its label, its kind and its help are data (`lib/isad.ts`), and the only thing a
 * screen chooses is *how* it edits a date — the dossier corrects the parsed ISO value, the form
 * accepts the spelling the archivist has in front of them ("Década de 1980"), which the API parses
 * with the language profile.
 */
export function IsadFieldControl({
  field,
  value,
  languages,
  onChange,
  hint,
  dateAs = "iso",
}: {
  field: IsadField;
  value: string;
  languages: readonly Language[];
  onChange: (value: string) => void;
  /** Overrides the catalogue's help, or adds a fact about this record ("como está na fonte"). */
  hint?: string;
  dateAs?: "iso" | "expression";
}) {
  const wide = field.control === "long_text" ? "sm:col-span-2" : "";

  return (
    <Field label={field.label} hint={hint} className={wide}>
      {field.control === "long_text" ? (
        <Textarea rows={3} value={value} onChange={(event) => onChange(event.target.value)} />
      ) : field.control === "language" ? (
        <LanguageSelect value={value} languages={languages} onChange={onChange} />
      ) : field.control === "date" && dateAs === "iso" ? (
        <Input type="date" value={value} onChange={(event) => onChange(event.target.value)} />
      ) : (
        <Input
          type="text"
          value={value}
          placeholder={field.control === "date" ? "Ex.: 1985-03-14, década de 1980 ou intervalo" : undefined}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </Field>
  );
}

/**
 * The language select, which keeps a value the catalogue does not know.
 *
 * A source declares "Português", "port." or a language the list does not carry; a bare ``select``
 * would render empty and saving would erase what the origin said. The current value travels as an
 * option of its own, marked, until the archivist replaces it.
 */
export function LanguageSelect({
  value,
  languages,
  onChange,
}: {
  value: string;
  languages: readonly Language[];
  onChange: (value: string) => void;
}) {
  const known = value === "" || languages.some((language) => language.name === value);

  return (
    <Select value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">— não informado —</option>
      {known ? null : <option value={value}>{value} (fora da lista)</option>}
      {languages.map((language) => (
        <option key={language.code} value={language.name}>
          {language.name}
        </option>
      ))}
    </Select>
  );
}
