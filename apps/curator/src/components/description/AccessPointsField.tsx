import { Plus, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import type { AccessPointPreviewItem } from "@/api/client";
import { cn } from "@/lib/cn";

/** One chip: the spelling the archivist typed or picked, and a key for React. */
export type AccessPointChip = { key: string; name: string };

/** One tag the type-ahead found: the id, the name and the context the screen chose to show. */
export type AccessPointSuggestion = { tagId: number; name: string; hint?: string };

/**
 * Everything the control says, supplied by the screen.
 *
 * The control is deliberately copy-free: the screen owns the Portuguese (and #227 will move it to
 * the i18n catalogue), so this file can be edited without touching the copy ratchet.
 */
export type AccessPointsCopy = {
  placeholder: string;
  add: (term: string) => string;
  remove: (name: string) => string;
  searching: string;
  searchFailed: string;
  duplicate: (term: string) => string;
  previewFailed: string;
};

/**
 * Access points as chips over the tag catalogue, with one summary of what the transfer will do.
 *
 * The type-ahead is the primary path: what already exists is picked, with the spelling and weight
 * the catalogue carries. What does not exist is typed and added by the explicit "add" option — the
 * archivist's spelling stays. The chips are never rewritten or removed behind their back: the
 * summary below the control says which spellings the transfer will create, map to a synonym or
 * discard, and the person decides whether to remove one.
 *
 * The preview is one request for the settled string, not one per chip: it is a read of the same
 * classifier the transfer uses, and its only job is the summary. A failed preview is a sentence,
 * not a broken control; the names still go to the server as typed.
 */
export function AccessPointsField({
  id,
  chips,
  onChange,
  search,
  preview,
  describe,
  copy,
  describedBy,
  searchDelayMs = 250,
  previewDelayMs = 300,
  disabled,
}: {
  id: string;
  chips: AccessPointChip[];
  onChange: (chips: AccessPointChip[]) => void;
  search: (term: string) => Promise<AccessPointSuggestion[]>;
  preview: (indexingPoints: string) => Promise<AccessPointPreviewItem[]>;
  describe: (items: AccessPointPreviewItem[]) => ReactNode;
  copy: AccessPointsCopy;
  describedBy?: string;
  searchDelayMs?: number;
  previewDelayMs?: number;
  disabled?: boolean;
}) {
  const [term, setTerm] = useState("");
  const [suggestions, setSuggestions] = useState<AccessPointSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const [items, setItems] = useState<AccessPointPreviewItem[]>([]);
  const [previewFailed, setPreviewFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const searchRequest = useRef(0);
  const previewRequest = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const searchRef = useRef(search);
  const previewRef = useRef(preview);
  const listId = useId();
  const summaryId = useId();

  useEffect(() => {
    searchRef.current = search;
    previewRef.current = preview;
  });

  useEffect(() => {
    const needle = term.trim();
    const mine = ++searchRequest.current;

    // Every state update lives inside the timer: a synchronous `setState` in an effect body
    // cascades a render on each keystroke, which is the rule the SPA's lint enforces.
    const timer = setTimeout(() => {
      if (!needle) {
        setSuggestions([]);
        setSearching(false);
        setSearchFailed(false);
        return;
      }

      setSearching(true);
      void searchRef
        .current(needle)
        .then((results) => {
          if (mine !== searchRequest.current) return;
          setSuggestions(results);
          setSearchFailed(false);
          setHighlighted(0);
          setSearching(false);
        })
        .catch(() => {
          if (mine !== searchRequest.current) return;
          setSuggestions([]);
          setSearchFailed(true);
          setSearching(false);
        });
    }, searchDelayMs);

    return () => clearTimeout(timer);
  }, [term, searchDelayMs]);

  const joined = chips.map((chip) => chip.name).join(", ");

  useEffect(() => {
    const mine = ++previewRequest.current;

    const timer = setTimeout(() => {
      if (!joined.trim()) {
        setItems([]);
        setPreviewFailed(false);
        return;
      }

      void previewRef
        .current(joined)
        .then((next) => {
          if (mine !== previewRequest.current) return;
          setItems(next);
          setPreviewFailed(false);
        })
        .catch(() => {
          if (mine !== previewRequest.current) return;
          setItems([]);
          setPreviewFailed(true);
        });
    }, previewDelayMs);

    return () => clearTimeout(timer);
  }, [joined, previewDelayMs]);

  function addSegments(raw: string) {
    const segments = raw
      .split(/[,;|\n]+/)
      .map((part) => part.trim())
      .filter(Boolean);
    if (segments.length === 0) return;

    const seen = new Set(chips.map((chip) => chip.name.trim().toLowerCase()));
    const next = [...chips];
    let duplicate: string | null = null;

    for (const segment of segments) {
      const key = segment.toLowerCase();
      if (seen.has(key)) {
        duplicate = segment;
        continue;
      }
      seen.add(key);
      next.push({ key: crypto.randomUUID(), name: segment });
    }

    setNotice(duplicate ? copy.duplicate(duplicate) : null);
    if (next.length !== chips.length) onChange(next);
    setTerm("");
    setSuggestions([]);
    setOpen(false);
    setHighlighted(0);
    inputRef.current?.focus();
  }

  function removeChip(key: string) {
    setNotice(null);
    onChange(chips.filter((chip) => chip.key !== key));
    inputRef.current?.focus();
  }

  const typed = term.trim();
  const exact = suggestions.some((suggestion) => suggestion.name.trim().toLowerCase() === typed.toLowerCase());
  const showAdd = typed.length > 0 && !exact;
  const options: Array<{ kind: "tag"; suggestion: AccessPointSuggestion } | { kind: "add" }> = [
    ...suggestions.map((suggestion) => ({ kind: "tag" as const, suggestion })),
    ...(showAdd ? [{ kind: "add" as const }] : []),
  ];
  const activeIndex = Math.min(highlighted, Math.max(options.length - 1, 0));
  const listOpen = open && typed.length > 0;
  const summary = notice ?? (previewFailed ? copy.previewFailed : describe(items));
  const describedByIds = [describedBy, summary ? summaryId : null].filter(Boolean).join(" ");

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        setHighlighted(0);
        return;
      }
      setHighlighted((current) => Math.min(current + 1, Math.max(options.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const option = options[activeIndex];
      if (listOpen && option) {
        addSegments(option.kind === "tag" ? option.suggestion.name : term);
      } else {
        addSegments(term);
      }
    } else if (event.key === "," || event.key === ";" || event.key === "|") {
      event.preventDefault();
      addSegments(term);
    } else if (event.key === "Escape") {
      setOpen(false);
    } else if (event.key === "Backspace" && term.length === 0 && chips.length > 0) {
      event.preventDefault();
      const last = chips.at(-1);
      if (last) removeChip(last.key);
    }
  }

  function onPaste(event: React.ClipboardEvent<HTMLInputElement>) {
    const text = event.clipboardData.getData("text");
    if (!/[,;|\n]/.test(text)) return;
    event.preventDefault();
    addSegments(text);
  }

  return (
    <div className="relative flex flex-col gap-1">
      <div
        className={cn(
          "access-points-box flex flex-wrap items-center gap-1 rounded-md bg-white px-2 py-1.5 ring-1 ring-(--color-line)",
          disabled ? "opacity-60" : null,
        )}
      >
        {chips.map((chip) => (
          <span key={chip.key} className="inline-flex items-center gap-1 rounded bg-black/5 px-2 py-0.5 text-xs">
            <span className="max-w-64 truncate">{chip.name}</span>
            <button
              type="button"
              aria-label={copy.remove(chip.name)}
              disabled={disabled}
              onClick={() => removeChip(chip.key)}
              className="rounded p-0.5 text-(--color-muted) hover:text-(--color-danger) focus:ring-2 focus:ring-(--color-accent) focus:outline-none"
            >
              <X className="size-3" aria-hidden />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          id={id}
          value={term}
          disabled={disabled}
          placeholder={copy.placeholder}
          role="combobox"
          aria-expanded={listOpen}
          aria-controls={listOpen ? listId : undefined}
          aria-autocomplete="list"
          aria-activedescendant={listOpen && options.length > 0 ? `${listId}-option-${activeIndex}` : undefined}
          aria-describedby={describedByIds || undefined}
          autoComplete="off"
          className="access-points-input min-w-32 flex-1 bg-transparent text-sm outline-none placeholder:text-(--color-muted)/70"
          onChange={(event) => {
            setTerm(event.target.value);
            setOpen(true);
            setNotice(null);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            setTimeout(() => setOpen(false), 150);
          }}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
        />
      </div>

      {listOpen ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute top-full z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md bg-(--color-surface) py-1 text-sm shadow-lg ring-1 ring-(--color-line)"
        >
          {searching && suggestions.length === 0 ? (
            <li className="px-3 py-2 text-xs text-(--color-muted)">{copy.searching}</li>
          ) : null}
          {!searching && searchFailed ? (
            <li className="px-3 py-2 text-xs text-(--color-danger)">{copy.searchFailed}</li>
          ) : null}
          {suggestions.map((suggestion, index) => (
            <li
              key={suggestion.tagId}
              id={`${listId}-option-${index}`}
              role="option"
              aria-selected={index === activeIndex}
            >
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setHighlighted(index)}
                onClick={() => addSegments(suggestion.name)}
                className={cn(
                  "flex w-full items-baseline justify-between gap-3 px-3 py-1.5 text-left",
                  index === activeIndex ? "bg-(--color-accent)/10" : "hover:bg-black/[0.04]",
                )}
              >
                <span className="min-w-0 truncate">{suggestion.name}</span>
                {suggestion.hint ? (
                  <span className="shrink-0 text-xs tabular-nums text-(--color-muted)">{suggestion.hint}</span>
                ) : null}
              </button>
            </li>
          ))}
          {showAdd ? (
            <li
              id={`${listId}-option-${suggestions.length}`}
              role="option"
              aria-selected={activeIndex === suggestions.length}
            >
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onMouseEnter={() => setHighlighted(suggestions.length)}
                onClick={() => addSegments(term)}
                className={cn(
                  "flex w-full items-center gap-2 border-t border-(--color-line) px-3 py-1.5 text-left",
                  activeIndex === suggestions.length ? "bg-(--color-accent)/10" : "hover:bg-black/[0.04]",
                )}
              >
                <Plus className="size-3.5 shrink-0 text-(--color-muted)" aria-hidden />
                <span className="min-w-0 truncate">{copy.add(typed)}</span>
              </button>
            </li>
          ) : null}
        </ul>
      ) : null}

      {summary ? (
        <div id={summaryId} role="status" aria-live="polite" className="text-xs text-(--color-muted)">
          {summary}
        </div>
      ) : null}
    </div>
  );
}
