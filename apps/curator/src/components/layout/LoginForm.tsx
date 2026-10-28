import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, login } from "@/api/client";
import { Lockup } from "@/components/brand/Lockup";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useCopy } from "@/i18n/context";
import { Trans } from "@/i18n/trans";

/**
 * The way in.
 *
 * It renders **inside the shell's place**, not on a route of its own, so a deep link survives the
 * sign-in: the archivist lands on `/acervo/lista`, signs in, and is on `/acervo/lista` — instead of
 * being bounced to `/entrar` and losing what they were sent.
 *
 * The failure is shown as one sentence, because that is what the API answers: an unknown address and a
 * wrong password are deliberately indistinguishable, and a screen that guessed between them would
 * undo that.
 *
 * The form is also the **front door of recovery**, and that is the whole of issue #26: the operation
 * exists — an administrator resets a password on the accounts screen, and the CLI on the host
 * recoloca the last administrator's — and what did not exist was anywhere to say so. The sentence under
 * the button only states the path; the disclosure under it says what a reset *does* (the temporary
 * password, the sessions that end, the lockout it lifts) and who holds the last resort. It never
 * promises a message this screen cannot send, because no e-mail is configured and none is sent:
 * pretending otherwise would leave somebody waiting for something that was never going to arrive.
 */
export function LoginForm() {
  const copy = useCopy();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const queryClient = useQueryClient();

  const signIn = useMutation({
    mutationFn: () => login(email, password),
    // The account the API answered with is the shell's data, so writing it here draws the shell
    // without a second request.
    onSuccess: (user) => queryClient.setQueryData(["current-user"], user),
  });

  const failure = signIn.error;

  return (
    <div className="flex min-h-full items-center justify-center px-4 py-10">
      <form
        className="w-full max-w-sm rounded-lg bg-(--color-surface) ring-1 ring-(--color-line)"
        onSubmit={(event) => {
          event.preventDefault();
          signIn.mutate();
        }}
      >
        {/*
          The identity, centred where the name used to be typed as plain text.

          The plate carries the same motif as the app's own header — the navy surface, the full
          lockup, the 2px terracotta rule — and it sits **inside the card**: this card is the whole
          screen, so a band across the window would have drawn a second frame around the one the card
          already draws. The name comes from `PRODUCT`, through `Lockup` — the same value the rail
          reads, so the front door cannot drift from the inside.
        */}
        <div className="mb-5 rounded-md border-b-2 border-(--color-brand) bg-(--color-rail) px-4 py-4 text-center">
          <Lockup className="ml-auto mr-8 h-20 w-auto text-(--color-rail-ink)" />
        </div>

        <div className="p-6">
          <label className="block pb-3 text-sm">
            <span className="pb-1 block text-(--color-muted)">{copy.auth.login.email}</span>
            <Input
              type="email"
              value={email}
              autoComplete="username"
              autoFocus
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label className="block pb-5 text-sm">
            <span className="pb-1 block text-(--color-muted)">{copy.auth.login.password}</span>
            <Input
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          {failure ? (
            <p className="pb-4 text-sm text-(--color-danger)">
              {failure instanceof ApiError ? failure.message : copy.auth.login.failure}
            </p>
          ) : null}

          <Button
            type="submit"
            variant="primary"
            className="w-full"
            disabled={signIn.isPending || !email || !password}
          >
            {signIn.isPending ? copy.auth.login.signingIn : copy.auth.login.signIn}
          </Button>

          {/*
          A native `details`, like the deletion trail's snapshot: the copy is one small block that must
          not push the form down, it works without JavaScript state, and the summary is a real
          disclosure control a screen reader announces as one.
        */}
          <details className="pt-3 text-xs">
            <summary className="cursor-pointer text-(--color-muted)">{copy.auth.login.forgot}</summary>
            <div className="grid gap-2 pt-2 text-(--color-muted)">
              <p>
                <Trans
                  text={copy.auth.login.noMessage}
                  values={{ settings: <strong>{copy.auth.login.settingsPath}</strong> }}
                />
              </p>
              <p>{copy.auth.login.lastAdmin}</p>
            </div>
          </details>
        </div>
      </form>
    </div>
  );
}
