import { useEffect, useRef, useState, type ReactNode } from "react";

import { PanelToggle } from "@/components/ui/PanelToggle";
import { useCopy } from "@/i18n/context";

/**
 * The panel an origin card is showing, and the click that reveals it (#234).
 *
 * `open` and `panel` are one piece of state split in two: the card's body exists only while the card
 * is open, and the form exists only inside the body. The action buttons used to set only `panel`, so
 * on a card that starts collapsed — every card does — the click armed a form nothing on screen could
 * read and the button felt dead. The rule now lives in one place, and one place is all it takes for
 * the next action added to the row to inherit it: **an action that reveals a panel also reveals the
 * card**, and clicking the action that is already open closes the panel without closing the card.
 *
 * The three units are separate because the card itself mounts queries and mutations: the state rule,
 * the action row and the region that scrolls itself into view are testable without a QueryClient.
 */
export type OriginPanel = "none" | "config" | "schedule";

export function useOriginPanel() {
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState<OriginPanel>("none");

  const reveal = (next: Exclude<OriginPanel, "none">) => {
    setOpen(true);
    setPanel((current) => (current === next ? "none" : next));
  };

  /** Closing the card resets the panel: reopening shows the facts, never a form nobody asked for. */
  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) setPanel("none");
  };

  return { open, panel, reveal, onOpenChange };
}

/** `Configurar` and `Agenda` as panel toggles; the shared `PanelToggle` carries the visible state. */
export function OriginPanelActions({
  panel,
  onSelect,
  configId,
  scheduleId,
}: {
  panel: OriginPanel;
  onSelect: (panel: Exclude<OriginPanel, "none">) => void;
  configId: string;
  scheduleId: string;
}) {
  const messages = useCopy();
  return (
    <>
      <PanelToggle
        label={messages.pages.origins.configure}
        active={panel === "config"}
        controls={configId}
        onSelect={() => onSelect("config")}
      />
      <PanelToggle
        label={messages.pages.origins.scheduleTab}
        active={panel === "schedule"}
        controls={scheduleId}
        onSelect={() => onSelect("schedule")}
      />
    </>
  );
}

/**
 * The open form, inside the card's body, brought into view by the click that revealed it.
 *
 * The card body also carries four facts and the run row, so on a long card the form would open
 * below the fold — "nothing happened" again, from the other direction. Scrolling the region rather
 * than the card keeps the reader on the form they asked for, and `block: "nearest"` moves the
 * screen the least it can.
 */
export function OriginPanelRegion({
  panel,
  configId,
  scheduleId,
  config,
  schedule,
}: {
  panel: OriginPanel;
  configId: string;
  scheduleId: string;
  config: ReactNode;
  schedule: ReactNode;
}) {
  const region = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (panel === "none") return;
    region.current?.scrollIntoView({ block: "nearest" });
  }, [panel]);

  if (panel === "none") return null;
  return (
    <div ref={region} id={panel === "config" ? configId : scheduleId}>
      {panel === "config" ? config : schedule}
    </div>
  );
}
