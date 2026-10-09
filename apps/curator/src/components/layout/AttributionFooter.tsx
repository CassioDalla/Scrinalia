import { ATTRIBUTION } from "@/lib/attribution";
import { PRODUCT } from "@/lib/copy";

/**
 * The page footer.
 *
 * Not decoration: the four elements below are the attribution that section 7(b) of the AGPL
 * requires any work based on this one — including a modified version — to keep displaying in its
 * Appropriate Legal Notices. `LICENSE-ADDITIONAL-TERMS.md` states the obligation; this is where
 * the reference implementation satisfies it.
 *
 * It is rendered by `AppShell`, so it appears on every screen without a route having to remember
 * it, and it must stay reachable without authenticating — a footer hidden behind a login is not a
 * notice to the users of a network service.
 */
export function AttributionFooter() {
  return (
    <footer className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-(--color-line) bg-(--color-surface) px-4 py-2 text-[11px] text-(--color-muted)">
      <span>{ATTRIBUTION.name}</span>
      <Separator />
      <span>
        © {ATTRIBUTION.year} {ATTRIBUTION.author}
      </span>
      <Separator />
      <span>{ATTRIBUTION.license}</span>
      <Separator />
      <a className="underline hover:text-(--color-ink)" href={ATTRIBUTION.licenseUrl} target="_blank" rel="noreferrer">
        Licença
      </a>
      <Separator />
      <a className="underline hover:text-(--color-ink)" href={ATTRIBUTION.sourceUrl} target="_blank" rel="noreferrer">
        Código-fonte
      </a>
      {/*
        The installation's version, alone at the far right and deliberately quiet.

        It is not attribution and it is not a link: it is the answer to "which build is this?", the
        question an operator asks when a screen behaves differently from the one in the issue. Quiet
        because it is read once and then never again — `opacity-60` on an 11px line — and separated
        by `ml-auto` so it cannot be read as part of the license notice beside it.
      */}
      <span className="ml-auto tabular-nums opacity-60" title="Versão da instalação">
        v{PRODUCT.version}
      </span>
    </footer>
  );
}

/** The dot between elements is decoration; a screen reader should not announce it. */
function Separator() {
  return <span aria-hidden="true">·</span>;
}
