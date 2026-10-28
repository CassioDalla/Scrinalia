import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, createFirstAdmin } from "@/api/client";
import { Lockup } from "@/components/brand/Lockup";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useCopy } from "@/i18n/context";

/**
 * The first screen of an installation that has no account at all.
 *
 * It replaces the sign-in form while `/setup/status` says `needs_setup`, and it renders in the same
 * place — inside the shell's slot, not on a route of its own — so the only thing that changes about
 * arriving is which form appears.
 *
 * Two deliberate choices about what it checks. The **confirmation** is compared in the browser,
 * because this password has no recovery by e-mail: a typo here costs a shell on the host, and it is
 * the one moment where checking twice is worth a field. The **policy** is not checked here at all:
 * the minimum length is a setting enforced in the domain, and the API's 422 sentence is how it
 * reaches the person — a second copy of the rule in this file would be a second place to be wrong.
 *
 * The account is created as an administrator by the API and signed in by the same answer, so the
 * success path is the shell, with no second sign-in.
 */
export function SetupForm() {
  const copy = useCopy();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const queryClient = useQueryClient();

  const create = useMutation({
    mutationFn: () => createFirstAdmin(email, name, password),
    onSuccess: (user) => {
      // The account the API answered with is the shell's data, and the installation is no longer
      // empty: writing both draws the shell without a second request, and without the gate asking
      // `/setup/status` again to discover the answer it just made true.
      queryClient.setQueryData(["current-user"], user);
      queryClient.setQueryData(["setup-status"], { needs_setup: false });
    },
  });

  const mismatch = confirmation.length > 0 && confirmation !== password;
  const failure = create.error;

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <form
        className="w-full max-w-sm rounded-lg bg-(--color-surface) ring-1 ring-(--color-line)"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        {/*
          The identity, centred at the top of the card, where this screen used to type the name as
          plain text. The same plate as the sign-in card and the same motif as the app's header: the
          navy surface, the full lockup, the 2px terracotta rule. The heading below stays — it says
          what this screen *is*, which the brand cannot.
        */}
        <div className="mb-5 rounded-md border-b-2 border-(--color-brand) bg-(--color-rail) px-4 py-4 text-center">
          <Lockup className="ml-auto mr-8 h-20 w-auto text-(--color-rail-ink)" />
        </div>

        <div className="p-6">
          <p className="pb-3 text-base font-semibold">{copy.auth.setup.title}</p>

          <p className="pb-4 text-xs text-(--color-muted)">{copy.auth.setup.explanation}</p>

          <label className="block pb-3 text-sm">
            <span className="pb-1 block text-(--color-muted)">{copy.auth.setup.email}</span>
            <Input
              type="email"
              value={email}
              autoComplete="username"
              autoFocus
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label className="block pb-3 text-sm">
            <span className="pb-1 block text-(--color-muted)">{copy.auth.setup.name}</span>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </label>

          <label className="block pb-3 text-sm">
            <span className="pb-1 block text-(--color-muted)">{copy.auth.setup.password}</span>
            <Input
              type="password"
              value={password}
              autoComplete="new-password"
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          <label className="block pb-5 text-sm">
            <span className="pb-1 block text-(--color-muted)">{copy.auth.setup.confirmation}</span>
            <Input
              type="password"
              value={confirmation}
              autoComplete="new-password"
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </label>

          {mismatch ? <p className="pb-4 text-sm text-(--color-danger)">{copy.auth.setup.mismatch}</p> : null}

          {failure ? (
            <p className="pb-4 text-sm text-(--color-danger)">
              {failure instanceof ApiError ? failure.message : copy.auth.setup.failure}
            </p>
          ) : null}

          <Button
            type="submit"
            variant="primary"
            className="w-full"
            disabled={create.isPending || !email || !name || !password || mismatch}
          >
            {create.isPending ? copy.auth.setup.creating : copy.auth.setup.create}
          </Button>

          <p className="pt-4 text-xs text-(--color-muted)">{copy.auth.setup.noRecovery}</p>
        </div>
      </form>
    </div>
  );
}
