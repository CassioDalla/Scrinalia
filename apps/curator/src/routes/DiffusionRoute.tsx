import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchCurrentUser } from "@/api/client";
import { queries } from "@/api/queries";
import { AddDiffusionChannelPanel } from "@/components/diffusion/AddDiffusionChannelPanel";
import { DiffusionChannelCard } from "@/components/diffusion/DiffusionChannelCard";
import { PageBody } from "@/components/layout/PageBody";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/Feedback";
import { useCopy } from "@/i18n/context";
import { fill } from "@/i18n/maps";
import { formatCount } from "@/lib/format";
import { can } from "@/lib/permissions";

/**
 * Canais de difusão: where the published collection can go.
 *
 * The operator's page, under Configurações → Operação, and the deliberate twin of Origens: one
 * screen says where the data comes in, this one says where the record leaves. The distinction the
 * page exists to make legible is that **a channel does not publish** — `is_published` is the
 * record's permission to leave, decided on the dossier under `CURATE`, and the channel is only the
 * destination. Adding, configuring and pausing are `OPERATE`; the read routes stay authenticated,
 * so a curator who follows a direct URL sees the cards read-only.
 *
 * The page reads every definition the package ships in one request and filters `configured` here,
 * so the add picker and the cards cannot disagree about what is still addable. The empty state is
 * real: the registry seeds no row (ADR 0023).
 */
export function DiffusionRoute() {
  const messages = useCopy();
  const { data, isPending, error } = useQuery(queries.diffusionChannels());
  const current = useQuery({ queryKey: ["current-user"], queryFn: fetchCurrentUser, retry: false });
  const role = current.data?.role ?? "VIEWER";
  const canOperate = can(role, "OPERATE");

  const [pickerOpen, setPickerOpen] = useState(false);
  const channels = data?.channels ?? [];
  const configured = channels.filter((channel) => channel.configured);
  const available = channels.filter((channel) => !channel.configured);
  const active = configured.filter((channel) => channel.enabled).length;

  return (
    <>
      <PageHeader
        screen="diffusion"
        pending={isPending}
        status={
          configured.length === 0
            ? messages.pages.diffusion.statusNone
            : fill(
                configured.length === 1
                  ? messages.pages.diffusion.statusOne
                  : messages.pages.diffusion.statusMany,
                { count: formatCount(configured.length), active: formatCount(active) },
              )
        }
        actions={
          canOperate && available.length > 0 && configured.length > 0 ? (
            <Button size="sm" variant="primary" onClick={() => setPickerOpen(true)}>
              {messages.pages.diffusion.addChannel}
            </Button>
          ) : null
        }
      />

      <PageBody className="gap-3">
        {error ? <ErrorState error={error} /> : null}

        {isPending ? (
          <div className="grid gap-3">
            <Skeleton className="h-40" />
          </div>
        ) : configured.length === 0 ? (
          <EmptyState
            title={messages.pages.diffusion.emptyTitle}
            hint={messages.pages.diffusion.emptyHint}
            action={
              canOperate && available.length > 0 ? (
                <Button size="sm" variant="primary" onClick={() => setPickerOpen(true)}>
                  {messages.pages.diffusion.addChannel}
                </Button>
              ) : canOperate ? (
                <p className="text-xs text-(--color-muted)">{messages.pages.diffusion.allConfigured}</p>
              ) : (
                <p className="text-xs text-(--color-muted)">{messages.pages.diffusion.operatorOnly}</p>
              )
            }
          />
        ) : (
          configured.map((channel) => (
            <DiffusionChannelCard key={channel.code} channel={channel} canOperate={canOperate} />
          ))
        )}

        {!isPending && configured.length > 0 && canOperate && available.length === 0 ? (
          <p className="text-xs text-(--color-muted)">{messages.pages.diffusion.allConfigured}</p>
        ) : null}
      </PageBody>

      {pickerOpen ? (
        <AddDiffusionChannelPanel available={available} onClose={() => setPickerOpen(false)} />
      ) : null}
    </>
  );
}
