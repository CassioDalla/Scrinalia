import { useEffect, useId, useRef, useState } from "react";

import { cn } from "@/lib/cn";

export type TypeaheadOption = {
  /** What the pick handler receives; always a string so the same component serves ids and codes. */
  value: string;
  label: string;
  hint?: string;
};

/**
 * A search box that asks the API as the archivist types and lets them pick one answer.
 *
 * It exists because two screens were asking for an **identifier** — the id of a tag, the code of a
 * parent — which is not something a person knows. Three rules are built in and not left to the
 * caller:
 *
 * * the search is debounced and the responses are guarded against arriving out of order, so the
 *   list cannot show the answer to a prefix the archivist already replaced;
 * * the floor of characters is *not* applied here — the API owns it, so every screen inherits the
 *   same one instead of each inventing its own;
 * * a term with no results says so, because an empty dropdown reads as a broken box.
 */
export function Typeahead({
  placeholder,
  onSearch,
  onPick,
  disabled,
  emptyLabel = "nada encontrado",
  className,
  autoFocus,
}: {
  placeholder: string;
  onSearch: (term: string) => Promise<TypeaheadOption[]>;
  onPick: (option: TypeaheadOption) => void;
  disabled?: boolean;
  emptyLabel?: string;
  className?: string;
  autoFocus?: boolean;
}) {
  const [term, setTerm] = useState("");
  const [options, setOptions] = useState<TypeaheadOption[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const [searched, setSearched] = useState(false);
  const listId = useId();

  // Monotonic request id: a slow answer to "igr" must not overwrite the answer to "igreja".
  const requestId = useRef(0);

  useEffect(() => {
    const needle = term.trim();
    // Every state update happens inside the timer, never in the effect body: a synchronous
    // ``setState`` there would cascade a render on each keystroke.
    const mine = ++requestId.current;

    const timer = setTimeout(
      () => {
        if (mine !== requestId.current) return;

        if (needle.length === 0) {
          setOptions([]);
          setSearched(false);
          setSearching(false);
          return;
        }

        setSearching(true);
        void onSearch(needle)
          .then((results) => {
            if (mine !== requestId.current) return;
            setOptions(results);
            setHighlighted(0);
            setSearched(true);
          })
          .catch(() => {
            if (mine !== requestId.current) return;
            setOptions([]);
            setSearched(true);
          })
          .finally(() => {
            if (mine === requestId.current) setSearching(false);
          });
      },
      needle.length === 0 ? 0 : 250,
    );

    return () => clearTimeout(timer);
  }, [term, onSearch]);

  const pick = (option: TypeaheadOption) => {
    onPick(option);
    setTerm("");
    setOptions([]);
    setOpen(false);
    setSearched(false);
  };

  return (
    <div className={cn("relative", className)}>
      <input
        value={term}
        disabled={disabled}
        autoFocus={autoFocus}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        placeholder={placeholder}
        onChange={(event) => {
          setTerm(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          // A small delay so a click on an option is not cancelled by the blur that precedes it.
          setTimeout(() => setOpen(false), 150);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setHighlighted((current) => Math.min(current + 1, Math.max(options.length - 1, 0)));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setHighlighted((current) => Math.max(current - 1, 0));
          } else if (event.key === "Enter") {
            event.preventDefault();
            const option = options[highlighted];
            if (option) pick(option);
          } else if (event.key === "Escape") {
            setOpen(false);
          }
        }}
        className={cn(
          "h-9 w-full rounded-md bg-white px-3 text-sm ring-1 ring-(--color-line) placeholder:text-(--color-muted)/70",
          "focus:ring-2 focus:ring-(--color-accent) focus:outline-none disabled:opacity-60",
        )}
      />

      {open && term.trim().length > 0 ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md bg-(--color-surface) py-1 text-sm shadow-lg ring-1 ring-(--color-line)"
        >
          {searching && options.length === 0 ? (
            <li className="px-3 py-2 text-xs text-(--color-muted)">buscando…</li>
          ) : null}

          {!searching && searched && options.length === 0 ? (
            <li className="px-3 py-2 text-xs text-(--color-muted)">{emptyLabel}</li>
          ) : null}

          {options.map((option, index) => (
            <li key={option.value} role="option" aria-selected={index === highlighted}>
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
                <span className="min-w-0 truncate">{option.label}</span>
                {option.hint ? (
                  <span className="shrink-0 text-xs tabular-nums text-(--color-muted)">{option.hint}</span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
