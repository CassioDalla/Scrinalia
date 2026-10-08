import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, changePassword } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

/**
 * Replacing the account's own password.
 *
 * Two situations, one form, and the difference is ``forced``: the CLI creates the first administrator
 * with a password it printed to a terminal, and that password must not become the account's permanent
 * one — so the shell shows this **instead of** the screens until it is replaced. The other way in is
 * voluntary, from the sidebar, which is what somebody does when they suspect the old password is known.
 *
 * The API ends every *other* session when the password changes and keeps this one, so nobody is
 * logged out of the screen they are standing on.
 */
export function PasswordChangeForm({
  forced = false,
  onDone,
}: {
  forced?: boolean;
  onDone?: () => void;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const queryClient = useQueryClient();

  const change = useMutation({
    mutationFn: () => changePassword(currentPassword, newPassword),
    onSuccess: () => {
      // The flag the shell reads is now false: refetch so the screens appear.
      void queryClient.invalidateQueries({ queryKey: ["current-user"] });
      onDone?.();
    },
  });

  const mismatch = confirmation.length > 0 && newPassword !== confirmation;
  const failure = change.error;

  return (
    <div className={forced ? "flex min-h-full items-center justify-center px-4 py-10" : ""}>
      <form
        className="w-full max-w-sm rounded-lg bg-(--color-surface) p-6 ring-1 ring-(--color-line)"
        onSubmit={(event) => {
          event.preventDefault();
          change.mutate();
        }}
      >
        <p className="text-base font-semibold">Trocar a senha</p>
        <p className="pb-5 text-sm text-(--color-muted)">
          {forced
            ? "Esta conta ainda usa a senha temporária criada no servidor. Escolha uma senha sua para continuar."
            : "As outras sessões desta conta serão encerradas."}
        </p>

        <label className="block pb-3 text-sm">
          <span className="pb-1 block text-(--color-muted)">Senha atual</span>
          <Input
            type="password"
            value={currentPassword}
            autoComplete="current-password"
            autoFocus
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
        </label>

        <label className="block pb-3 text-sm">
          <span className="pb-1 block text-(--color-muted)">Nova senha</span>
          <Input
            type="password"
            value={newPassword}
            autoComplete="new-password"
            onChange={(event) => setNewPassword(event.target.value)}
          />
        </label>

        <label className="block pb-5 text-sm">
          <span className="pb-1 block text-(--color-muted)">Repita a nova senha</span>
          <Input
            type="password"
            value={confirmation}
            autoComplete="new-password"
            onChange={(event) => setConfirmation(event.target.value)}
          />
        </label>

        {mismatch ? <p className="pb-4 text-sm text-(--color-danger)">As duas senhas não conferem.</p> : null}
        {failure ? (
          <p className="pb-4 text-sm text-(--color-danger)">
            {failure instanceof ApiError ? failure.message : "Não foi possível trocar a senha."}
          </p>
        ) : null}

        <div className="flex items-center gap-2">
          <Button
            type="submit"
            variant="primary"
            disabled={change.isPending || !currentPassword || !newPassword || mismatch}
          >
            {change.isPending ? "Salvando…" : "Trocar a senha"}
          </Button>
          {!forced && onDone ? (
            <Button type="button" variant="ghost" onClick={onDone}>
              Cancelar
            </Button>
          ) : null}
        </div>
      </form>
    </div>
  );
}
