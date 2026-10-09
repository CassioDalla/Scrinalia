import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/Feedback";
import { SCREENS, screenSubtitle, type ScreenId } from "@/lib/screens";

/**
 * The head of every screen, with the same four slots in the same order.
 *
 * The anatomy is fixed on purpose — a name, one line saying what the screen decides, the status of
 * what was read, and the actions — because before it the screens disagreed about all four. The
 * heading was sometimes the menu's word and sometimes a sentence; the explanatory line and the count
 * competed for the same slot, so a screen either explained itself or reported its totals, never both;
 * and the loading state was spelled `Lendo o vocabulário…` on one page and `Carregando…` on the next.
 *
 * **The heading is not a prop.** A screen says which screen it is — `screen="tags"` — and the name
 * and the subtitle come from `lib/screens.ts`, the same record the rail and the settings card read.
 * That is what makes the old divergence impossible rather than merely repaired: there is no longer a
 * string here to disagree with the menu. The dossier is the one exception, and it passes `title`
 * directly because its heading is the record's own title, which no catalogue can hold.
 *
 * `status` is the count the second line used to carry, now in its own muted line under the subtitle,
 * and `pending` is what takes its place while the read is in flight: a skeleton of the same height,
 * so the header does not jump when the numbers arrive and the page has one loading idiom instead of
 * the fifteen it had.
 */
type PageHeaderSlots = {
  /** What the screen read: a count, a filter, a total. Muted, under the subtitle. */
  status?: ReactNode;
  /** Whether the status is still being read. Takes the status slot; never both. */
  pending?: boolean;
  actions?: ReactNode;
};

type PageHeaderProps = PageHeaderSlots &
  (
    | { screen: ScreenId; title?: never; subtitle?: never }
    | { screen?: never; title: ReactNode; subtitle?: ReactNode }
  );

export function PageHeader(props: PageHeaderProps) {
  const { status, pending = false, actions } = props;
  const { title, subtitle } =
    props.screen !== undefined
      ? { title: SCREENS[props.screen].label, subtitle: screenSubtitle(props.screen) }
      : { title: props.title, subtitle: props.subtitle };

  return (
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-(--color-line) bg-(--color-surface) px-6 py-4">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-semibold">{title}</h1>
        {subtitle ? <div className="mt-0.5 text-sm text-(--color-muted)">{subtitle}</div> : null}
        {pending ? (
          <Skeleton className="mt-1.5 h-3.5 w-48" />
        ) : status ? (
          <div className="mt-1.5 text-xs text-(--color-muted)">{status}</div>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}
