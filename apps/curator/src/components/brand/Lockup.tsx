import { useId } from "react";

import { PRODUCT } from "@/lib/copy";

/**
 * The horizontal lockup: the mark, then the wordmark in **PT Serif**.
 *
 * It is inlined for the same reason as `Mark`, and for one more that decides the font: an SVG
 * loaded through `<img>` is its own document and has no access to the page's `@font-face`, so
 * `<text>` inside it renders with a font installed on the machine — PT Serif is installed nowhere,
 * and the wordmark would silently fall back to whatever the browser's default serif is. Inlined,
 * the page's font applies, and the wordmark is real text: selectable, searchable, and translated by
 * a screen reader as the word it is.
 *
 * The mark is drawn at the same geometry as `Mark` (see that file) rather than reused, because the
 * lockup scales it with the transform the identity file uses — `translate(-8.148 10.074)
 * scale(0.79012)` — and a nested `<svg>` would need that transform expressed twice.
 *
 * The colour comes from the parent: `fill-current`/`stroke-current` take the surface's text colour,
 * so the same component is cream on the rail and ink on paper. Only the tab is fixed — the identity's
 * terracotta, the one colour that does not change with the surface.
 */
export function Lockup({ className }: { className?: string }) {
  const id = useId();
  const clip = `scr-lockup-${id}`;
  const title = `scr-lockup-title-${id}`;

  return (
    <svg viewBox="0 0 300 96" role="img" aria-labelledby={title} className={className}>
      <title id={title}>{PRODUCT.name}</title>
      <defs>
        <clipPath id={clip}>
          <rect x="28" y="10" width="40" height="76" rx="10" />
        </clipPath>
      </defs>
      <g transform="translate(-8.148 10.074) scale(0.79012)">
        <rect x="28" y="10" width="40" height="25.333" className="fill-(--color-brand)" clipPath={`url(#${clip})`} />
        <g fill="none" strokeWidth="5" className="fill-none stroke-current">
          <rect x="28" y="10" width="40" height="76" rx="10" />
          <path d="M28 35.333H68" />
          <path d="M28 60.667H68" />
        </g>
      </g>
      {/*
        The wordmark's own numbers, from the identity file's style block: 45px, weight 400,
        -0.015em. `font-brand` is the `@font-face` in `styles.css` — the one definition of the
        logomark's serif.
      */}
      <text x="63.5" y="64" className="fill-current font-brand text-[45px] font-normal tracking-[-0.015em]">
        {PRODUCT.name}
      </text>
    </svg>
  );
}
