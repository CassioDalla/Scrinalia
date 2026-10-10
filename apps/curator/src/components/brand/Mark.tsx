import { useId } from "react";

import { PRODUCT } from "@/lib/copy";

/**
 * The cropped mark: the catalogue card with its coloured tab, and nothing around it.
 *
 * This is `assets/brand/marca-recorte.svg` — the identity's own crop, `viewBox="25.5 7.5 45 81"` —
 * inlined. It is not an `<img src="….svg">` for a reason that shows on the rail: a class, a `var()`
 * or a `currentColor` inside an SVG loaded through `<img>` cannot be reached by the page's CSS, so
 * the card could not take the surface's ink and the tab could not take the theme's terracotta.
 * Inlined, `stroke-current` follows the parent's text colour and the tab is one token away.
 *
 * It is the mark and not the lockup because the rail at 64px has no room for the word: this is what
 * stays when the words leave, and it is also the control that brings them back.
 *
 * The tiled variants — `marca-clara.svg`, `marca-escura.svg`, `marca-redonda.svg` — stay as design
 * sources and as the favicon; a surface that needs a tile draws it behind this, which is what the
 * favicon does.
 */
export function Mark({ className }: { className?: string }) {
  const id = useId();
  const clip = `scr-mark-${id}`;
  const title = `scr-mark-title-${id}`;

  return (
    <svg viewBox="25.5 7.5 45 81" role="img" aria-labelledby={title} className={className}>
      <title id={title}>{PRODUCT.name}</title>
      <defs>
        <clipPath id={clip}>
          <rect x="28" y="10" width="40" height="76" rx="10" />
        </clipPath>
      </defs>
      <rect x="28" y="10" width="40" height="25.333" className="fill-(--color-brand)" clipPath={`url(#${clip})`} />
      <g fill="none" strokeWidth="5" className="fill-none stroke-current">
        <rect x="28" y="10" width="40" height="76" rx="10" />
        <path d="M28 35.333H68" />
        <path d="M28 60.667H68" />
      </g>
    </svg>
  );
}
