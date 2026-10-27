import {
  Children,
  cloneElement,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";

import { Info } from "lucide-react";

import { cn } from "@/lib/cn";

type Align = "start" | "center" | "end";
type Placement = "top" | "bottom";

type CommonProps = {
  /** Where the panel starts, relative to the trigger. */
  align?: Align;
  /** Above the trigger for a label, below it for a row of tabs. */
  placement?: Placement;
  /** Extra classes on the inline wrapper, never on the floating panel. */
  className?: string;
};

type HintProps =
  | (CommonProps & {
      asChild?: false;
      /** The trigger's accessible name; it is icon-only, so this is the only name a reader gets. */
      label: string;
      /** The explanation. Text only: a tooltip never holds a link, a button or a form control. */
      children: ReactNode;
      text?: never;
    })
  | (CommonProps & {
      /** Render the single child as the trigger, instead of the default info icon. */
      asChild: true;
      /** The explanation, because the child is the trigger. */
      text: ReactNode;
      children: ReactElement;
      label?: never;
    });

type TriggerProps = {
  "aria-describedby"?: string;
  onClick?: React.MouseEventHandler<HTMLElement>;
};

const PANEL =
  "absolute z-50 w-max max-w-[min(16rem,calc(100vw-2rem))] rounded-md bg-(--color-surface) px-3 py-2 text-left text-xs leading-relaxed font-normal tracking-normal whitespace-normal text-(--color-ink) normal-case shadow-lg ring-1 ring-(--color-line)";

const PLACEMENT: Record<Placement, string> = {
  top: "bottom-full",
  bottom: "top-full",
};

const ALIGN: Record<Align, string> = {
  start: "left-0",
  center: "left-1/2 -translate-x-1/2",
  end: "right-0",
};

/**
 * A quiet, reusable explanation beside a label or a badge (#208).
 *
 * The native `title` was the default "discreet" pattern in this SPA and the weakest one: it appears
 * only on hover, after a delay, never on keyboard focus and never on touch, and its text is not
 * reliably exposed to assistive technology. This component is the replacement: a real button with
 * `aria-describedby` and a `role="tooltip"` panel that stays in the DOM (screen-reader hidden while
 * closed), so the same sentence is reachable by mouse, keyboard and touch.
 *
 * It is for **secondary** explanation. It is never the only description of a required field, a
 * destructive action or a governance rule — those stay visible under the control (`Field.hint`) or
 * in a `Notice`. A tooltip also holds no interactive content: when the text needs a link or a
 * button, the answer is `Disclosure`, not this.
 *
 * Open on hover and on focus, toggle on click/tap, close on Escape and on an outside pointer. The
 * tooltip never takes focus, so there is nothing to return: Escape leaves focus where it was, which
 * is the trigger when the keyboard opened it.
 */
export function Hint(props: HintProps) {
  const { align = "center", placement = "top", className } = props;
  const text = props.asChild ? props.text : props.children;
  const panelId = useId();
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [pinned, setPinned] = useState(false);
  /** Escape and an outside click close even while the pointer or the focus still rests on it. */
  const [dismissed, setDismissed] = useState(false);

  const open = !dismissed && (hovered || focused || pinned);

  const toggle = () => {
    if (open) {
      setPinned(false);
      setDismissed(true);
      return;
    }
    setPinned(true);
    setDismissed(false);
  };

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && wrapperRef.current?.contains(event.target)) return;
      setPinned(false);
      setHovered(false);
      setFocused(false);
      setDismissed(true);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  let trigger: ReactNode;
  if (props.asChild) {
    const child = Children.only(props.children) as ReactElement<TriggerProps>;
    const childOnClick = child.props.onClick;
    trigger = cloneElement(child, {
      "aria-describedby": [child.props["aria-describedby"], panelId].filter(Boolean).join(" "),
      onClick: (event: React.MouseEvent<HTMLElement>) => {
        childOnClick?.(event);
        toggle();
      },
    });
  } else {
    trigger = (
      <button
        type="button"
        aria-label={props.label}
        aria-describedby={panelId}
        onClick={toggle}
        className="relative inline-grid size-5 shrink-0 place-items-center rounded-full text-(--color-muted) transition after:absolute after:-inset-1 after:content-[''] hover:bg-black/5 hover:text-(--color-ink)"
      >
        <Info aria-hidden size={13} strokeWidth={2.25} />
      </button>
    );
  }

  return (
    <span
      ref={wrapperRef}
      role="presentation"
      className={cn("relative inline-flex align-middle", className)}
      onMouseEnter={() => {
        setHovered(true);
        setDismissed(false);
      }}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => {
        setFocused(true);
        setDismissed(false);
      }}
      onBlur={(event) => {
        if (event.currentTarget.contains(event.relatedTarget)) return;
        setFocused(false);
        setPinned(false);
      }}
      onKeyDown={(event) => {
        if (event.key !== "Escape" || !open) return;
        event.stopPropagation();
        setPinned(false);
        setFocused(false);
        setDismissed(true);
      }}
    >
      {trigger}
      <span
        id={panelId}
        role="tooltip"
        data-state={open ? "open" : "closed"}
        className={open ? cn(PANEL, PLACEMENT[placement], ALIGN[align]) : "sr-only"}
      >
        {text}
      </span>
    </span>
  );
}
