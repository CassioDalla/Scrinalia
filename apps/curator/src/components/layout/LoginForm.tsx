import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, login } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ATTRIBUTION } from "@/lib/attribution";

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
 */
export function LoginForm() {
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
        className="w-full max-w-sm rounded-lg bg-(--color-surface) p-6 ring-1 ring-(--color-line)"
        onSubmit={(event) => {
          event.preventDefault();
          signIn.mutate();
        }}
      >
        <p className="text-lg font-semibold">{ATTRIBUTION.name}</p>
        <p className="pb-5 text-sm text-(--color-muted)">Curadoria do acervo</p>

        <label className="block pb-3 text-sm">
          <span className="pb-1 block text-(--color-muted)">E-mail</span>
          <Input
            type="email"
            value={email}
            autoComplete="username"
            autoFocus
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>

        <label className="block pb-5 text-sm">
          <span className="pb-1 block text-(--color-muted)">Senha</span>
          <Input
            type="password"
            value={password}
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>

        {failure ? (
          <p className="pb-4 text-sm text-(--color-danger)">
            {failure instanceof ApiError ? failure.message : "Não foi possível entrar."}
          </p>
        ) : null}

        <Button
          type="submit"
          variant="primary"
          className="w-full"
          disabled={signIn.isPending || !email || !password}
        >
          {signIn.isPending ? "Entrando…" : "Entrar"}
        </Button>

        <p className="pt-4 text-xs text-(--color-muted)">
          Não há recuperação de senha por e-mail: quem administra a instalação redefine a sua senha.
        </p>
      </form>
    </div>
  );
}
