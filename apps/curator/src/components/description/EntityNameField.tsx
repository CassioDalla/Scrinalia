import { useEffect, useId, useRef, useState } from "react";

import { searchEntities, type EntityRelevance } from "@/api/client";
import { Input } from "@/components/ui/Input";
import { useCopy } from "@/i18n/context";
import { cn } from "@/lib/cn";
import { descricoes } from "@/lib/format";

/**
 * ``Produtor(es)`` as a name autocomplete over the entity catalogue (#230).
 *
 * The catalogue knows the spelling the NER canonicalised; the archivist knows who produced the
 * fonds. This control lets the second read the first: typing asks the entity search, and picking a
 * suggestion **copies its name into the text**. It is a convenience, not a link — no ``entity_id``
 * travels, so a merge or a rename later does not reach the description, which is the relation's job
 * (#242), not this field's.
 *
 * Three rules are built in and not left to the screen:
 *
 * * the copy is **verbatim**, the name exactly as the catalogue stores it (lowercase, see
 *   ``normalize_entity``); the field stays a plain text the archivist can keep editing, and nothing
 *   is silently rewritten into another case;
 * * picking replaces only the **fragment around the caret**, the text between two separators, so
 *   "Câmara…, gui" becomes "Câmara…, guido ghilardi" and the archivist's own punctuation and spacing
 *   survive — no separator is imposed by this widget;
 * * a term the catalogue does not have stays typeable: the list is a suggestion, never a gate.
 *
 * The four sentences this control owns are catalogue messages (``producers``), because ADR 0020 §7
 * extracts the interface file by file and a new file starts inside the catalogue, not in the
 * pending list.
 */

/** Where one producer ends and the next begins, when the archivist writes several. */
const SEPARATORS = [",", ";", "|", "\n"];

/**
 * The fragment that contains the caret, trimmed: the name the archivist is typing or editing.
 *
 * The replacement keeps everything outside it — the separators, the spaces and the other names — so
 * the control never has to decide how several producers are written down.
 */
export function segmentAt(text: string, caret: number): { start: number; end: number; term: string } {
  let from = caret;
  let to = caret;

  while (from > 0 && !SEPARATORS.includes(text[from - 1] ?? "")) from -= 1;
  while (to < text.length && !SEPARATORS.includes(text[to] ?? "")) to += 1;

  let start = from;
  let end = to;
  while (start < end && (text[start] ?? "").trim() === "") start += 1;
  while (end > start && (text[end - 1] ?? "").trim() === "") end -= 1;

  return { start, end, term: text.slice(start, end) };
}

/** The option's second line: what the catalogue knows about the name it is offering. */
function hintFor(entity: EntityRelevance): string {
  return `${entity.entity_type} · ${descricoes(entity.total_usage)}`;
}

export function EntityNameField({
  id,
  value,
  onChange,
  search = searchEntities,
  describedBy,
  searchDelayMs = 250,
  disabled,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  /** The entity search; the default is the API, and a test can hand in its own. */
  search?: (term: string) => Promise<EntityRelevance[]>;
  describedBy?: string;
  searchDelayMs?: number;
  disabled?: boolean;
}) {
  const copy = useCopy().producers;
  const [needle, setNeedle] = useState("");
  const [options, setOptions] = useState<EntityRelevance[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [failed, setFailed] = useState(false);
  const [searched, setSearched] = useState(false);
  const [highlighted, setHighlighted] = useState(0);

  const requestId = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingCaret = useRef<number | null>(null);
  const searchRef = useRef(search);

  const listId = useId();
  const listOpen = open && needle.trim().length > 0;

  useEffect(() => {
    searchRef.current = search;
  });

  useEffect(() => {
    const term = needle.trim();
    // Every state update lives inside the timer: a synchronous `setState` in an effect body would
    // cascade a render on each keystroke, which is the rule the SPA's lint enforces.
    const mine = ++requestId.current;

    const timer = setTimeout(() => {
      if (mine !== requestId.current) return;

      if (term.length === 0) {
        setOptions([]);
        setSearched(false);
        setSearching(false);
        setFailed(false);
        return;
      }

      setSearching(true);
      void searchRef
        .current(term)
        .then((results) => {
          if (mine !== requestId.current) return;
          setOptions(results);
          setHighlighted(0);
          setSearched(true);
          setFailed(false);
        })
        .catch(() => {
          if (mine !== requestId.current) return;
          setOptions([]);
          setSearched(true);
          setFailed(true);
        })
        .finally(() => {
          if (mine === requestId.current) setSearching(false);
        });
    }, searchDelayMs);

    return () => clearTimeout(timer);
  }, [needle, searchDelayMs]);

  // The caret lands after the copied name once the parent has applied the new value.
  useEffect(() => {
    const caret = pendingCaret.current;
    if (caret === null) return;
    pendingCaret.current = null;
    const input = inputRef.current;
    input?.focus();
    input?.setSelectionRange(caret, caret);
  }, [value]);

  function pick(entity: EntityRelevance) {
    const input = inputRef.current;
    const caret = input?.selectionStart ?? value.length;
    const { start, end } = segmentAt(value, caret);
    const next = `${value.slice(0, start)}${entity.name}${value.slice(end)}`;

    pendingCaret.current = start + entity.name.length;
    onChange(next);

    setNeedle("");
    setOptions([]);
    setOpen(false);
    setSearched(false);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!listOpen) return;
      setHighlighted((current) => Math.min(current + 1, Math.max(options.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!listOpen) return;
      setHighlighted((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      const option = options[highlighted];
      if (listOpen && option) {
        event.preventDefault();
        pick(option);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <div className="relative">
      <Input
        ref={inputRef}
        id={id}
        value={value}
        disabled={disabled}
        placeholder={copy.placeholder}
        role="combobox"
        aria-expanded={listOpen}
        aria-controls={listOpen ? listId : undefined}
        aria-autocomplete="list"
        aria-activedescendant={listOpen && options.length > 0 ? `${listId}-option-${highlighted}` : undefined}
        aria-describedby={describedBy}
        autoComplete="off"
        onChange={(event) => {
          const next = event.target.value;
          const caret = event.target.selectionStart ?? next.length;
          onChange(next);
          setNeedle(segmentAt(next, caret).term);
          setOpen(true);
        }}
        onFocus={() => {
          // Only reopens a list that is already answering: focusing an existing record must not
          // pop a dropdown over text the archivist came to read.
          if (listOpen) setOpen(true);
        }}
        onBlur={() => {
          // A small delay so a click on an option is not cancelled by the blur that precedes it.
          setTimeout(() => setOpen(false), 150);
        }}
        onKeyDown={onKeyDown}
      />

      {listOpen ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute top-full z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md bg-(--color-surface) py-1 text-sm shadow-lg ring-1 ring-(--color-line)"
        >
          {searching && options.length === 0 ? (
            <li className="px-3 py-2 text-xs text-(--color-muted)">{copy.searching}</li>
          ) : null}

          {!searching && failed ? (
            <li className="px-3 py-2 text-xs text-(--color-danger)">{copy.failed}</li>
          ) : null}

          {!searching && !failed && searched && options.length === 0 ? (
            <li className="px-3 py-2 text-xs text-(--color-muted)">{copy.empty}</li>
          ) : null}

          {options.map((option, index) => (
            <li
              key={option.entity_id}
              id={`${listId}-option-${index}`}
              role="option"
              aria-selected={index === highlighted}
            >
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setHighlighted(index)}
                onClick={() => pick(option)}
                className={cn(
                  "flex w-full items-baseline justify-between gap-3 px-3 py-1.5 text-left",
                  index === highlighted ? "bg-(--color-accent)/10" : "hover:bg-black/[0.04]",
                )}
              >
                <span className="min-w-0 truncate">{option.name}</span>
                <span className="shrink-0 text-xs tabular-nums text-(--color-muted)">{hintFor(option)}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
