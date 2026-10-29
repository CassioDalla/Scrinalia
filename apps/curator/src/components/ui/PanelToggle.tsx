import { Button } from "@/components/ui/Button";

/**
 * A card action that opens a form below it, and says whether that form is the one on screen.
 *
 * The visible state is a pair on purpose — the outlined, accent-tinted button with a downward
 * chevron is the one whose form is below, so "which panel is this card showing?" is answerable from
 * the header alone, on a long card whose body starts below the fold. `aria-controls` is set only
 * while the region exists: pointing at an absent id is a promise with nothing behind it.
 *
 * It was born inside the origins card (#206) and is shared now that the diffusion card needs the
 * same gesture (#213): two copies of this rule would be two places for the chevron to stop matching
 * the panel.
 */
export function PanelToggle({
  label,
  active,
  controls,
  onSelect,
}: {
  label: string;
  active: boolean;
  controls: string;
  onSelect: () => void;
}) {
  return (
    <Button
      size="sm"
      variant={active ? "secondary" : "ghost"}
      aria-expanded={active}
      aria-controls={active ? controls : undefined}
      onClick={onSelect}
      className={active ? "text-(--color-accent) ring-(--color-accent)/40" : undefined}
    >
      <span aria-hidden className="text-[10px]">
        {active ? "▾" : "▸"}
      </span>
      {label}
    </Button>
  );
}
