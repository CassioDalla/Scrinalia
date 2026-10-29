import { useState } from "react";

import type { DiffusionChannel } from "@/api/client";
import { DiffusionConfigForm } from "@/components/diffusion/DiffusionConfigForm";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Feedback";
import { SidePanel, SidePanelClose } from "@/components/ui/SidePanel";
import { useCopy } from "@/i18n/context";
import { stringMap } from "@/i18n/maps";

const CAPABILITY_LABEL = stringMap((m) => ({
  LIVE: m.pages.diffusion.capabilityLive,
  EXPORT: m.pages.diffusion.capabilityExport,
}));

/**
 * The picker of definitions this installation has no row for, and the form that adds one.
 *
 * The registry is code: the operator selects a channel the package ships, and this panel does not
 * invent an adapter. The picker grows when the dataset adapter lands (#214) and AtoM only when its
 * adapter exists — a definition the package does not ship is not an option here.
 *
 * **The add is one gesture with two halves.** A new channel needs its configuration in the same
 * `PATCH` that creates the row, because the service refuses a row it cannot validate (`site_title`
 * is required) — so choosing a definition opens the generic form, and saving sends
 * `{enabled: true, config}`. The form is the same renderer the card edits with; there is no second
 * definition of what a channel's configuration is.
 */
export function AddDiffusionChannelPanel({
  available,
  onClose,
}: {
  available: DiffusionChannel[];
  onClose: () => void;
}) {
  const messages = useCopy();
  const [selected, setSelected] = useState<DiffusionChannel | null>(null);

  return (
    <SidePanel
      label={messages.pages.diffusion.addTitle}
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-(--color-muted)">{messages.pages.diffusion.addNote}</span>
          <Button size="sm" variant="ghost" onClick={onClose}>
            {messages.common.close}
          </Button>
        </div>
      }
    >
      <div className="grid gap-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">{messages.pages.diffusion.addTitle}</h2>
            <p className="mt-0.5 text-xs text-(--color-muted)">
              {selected ? selected.label : messages.pages.diffusion.addHint}
            </p>
          </div>
          <SidePanelClose onClose={onClose} />
        </div>

        {selected ? (
          <>
            <div>
              <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>
                ← {messages.pages.diffusion.back}
              </Button>
            </div>
            <DiffusionConfigForm channel={selected} mode="create" onSaved={onClose} />
          </>
        ) : available.length === 0 ? (
          <EmptyState
            title={messages.pages.diffusion.allConfigured}
            hint={messages.pages.diffusion.addHint}
          />
        ) : (
          available.map((item) => (
            <Card key={item.code}>
              <CardBody className="grid gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{item.label}</span>
                  <Badge tone="neutral">{CAPABILITY_LABEL[item.capability]}</Badge>
                </div>
                <p className="text-xs text-(--color-muted)">{item.description}</p>
                <div>
                  <Button size="sm" variant="primary" onClick={() => setSelected(item)}>
                    {messages.pages.diffusion.add}
                  </Button>
                </div>
              </CardBody>
            </Card>
          ))
        )}
      </div>
    </SidePanel>
  );
}
