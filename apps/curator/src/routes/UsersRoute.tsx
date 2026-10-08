import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  createUser,
  fetchCurrentUser,
  resetUserPassword,
  revokeUserSession,
  revokeUserSessions,
  updateUser,
  type AuthUser,
  type UpdateUserRequest,
} from "@/api/client";
import { queries } from "@/api/queries";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Disclosure } from "@/components/ui/Disclosure";
import { ErrorState, Skeleton } from "@/components/ui/Feedback";
import { Input, Select } from "@/components/ui/Input";
import { formatDateTime } from "@/lib/format";
import { routeMessage } from "@/lib/messages";
import { ROLE_LABEL, ROLES } from "@/lib/permissions";

/**
 * The accounts of the installation — the surface of `Permission.ADMIN`.
 *
 * Three facts the API enforces and the screen has to say rather than let the archivist discover
 * through a refusal:
 *
 * * **the password created here is temporary.** The administrator typed it, so the account replaces
 *   it at the first sign-in — the same rule the CLI applies to the bootstrap account;
 * * **deactivating ends every session of the account immediately.** The flag alone would let
 *   whoever holds the cookie keep working until it expired;
 * * **the last active administrator cannot be deactivated or demoted.** It is the one lockout with
 *   no way back through the screen, and the way in is the CLI on the host.
 *
 * There is no delete. An account is deactivated, because the ledgers carry its name and its id: a
 * decision whose author no longer exists is a worse record than a closed account.
 */
export function UsersRoute() {
  const queryClient = useQueryClient();
  const users = useQuery(queries.users());
  // The signed-in account, to mark "você" on its own row. Read from the shell's cache, so it costs
  // nothing and cannot disagree with the menu the person is looking at.
  const current = useQuery({ queryKey: ["current-user"], queryFn: fetchCurrentUser, retry: false });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["identity", "users"] });

  const rows = users.data ?? [];
  const active = rows.filter((row) => row.is_active).length;

  return (
    <>
      <PageHeader
        title="Contas"
        subtitle={
          users.data ? `${rows.length} contas · ${active} ativas` : "Lendo as contas…"
        }
      />

      <div className="grid max-w-5xl gap-4 px-6 py-5">
        <p className="rounded-md bg-(--color-accent)/5 px-3 py-2 text-xs text-(--color-accent) ring-1 ring-(--color-accent)/20">
          A senha criada aqui é <strong>temporária</strong>: a conta troca no primeiro acesso. Desativar
          encerra todas as sessões na hora, e a última conta de administrador ativa não pode ser
          desativada nem rebaixada — é o único beco sem saída que não tem volta pela tela.
        </p>

        {users.error ? <ErrorState error={users.error} /> : null}
        {users.isPending ? (
          <div className="grid gap-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-16" />
            ))}
          </div>
        ) : null}

        <CreateUserCard onCreated={invalidate} />

        <section className="grid gap-2">
          {rows.map((user) => (
            <UserCard
              key={user.user_id}
              user={user}
              isSelf={current.data?.user_id === user.user_id}
              onChanged={invalidate}
            />
          ))}
        </section>
      </div>
    </>
  );
}

function CreateUserCard({ onCreated }: { onCreated: () => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<AuthUser["role"]>("CURATOR");
  const [password, setPassword] = useState("");

  const create = useMutation({
    mutationFn: () => createUser({ email: email.trim(), name: name.trim(), role, password }),
    onSuccess: () => {
      setEmail("");
      setName("");
      setRole("CURATOR");
      setPassword("");
      onCreated();
    },
  });

  const valid = email.trim().length >= 3 && name.trim().length > 0 && password.length > 0;

  return (
    <Disclosure
      triggerLabel="+ Nova conta"
      toggleLabel="Criar uma conta"
      header={
        <div className="grid gap-1">
          <span className="text-sm font-semibold">Criar uma conta</span>
          <span className="text-xs text-(--color-muted)">
            O papel decide o que a conta alcança; a senha é temporária e a política é verificada pelo
            servidor.
          </span>
        </div>
      }
    >
      <div className="grid gap-2">
        <div className="grid gap-2 sm:grid-cols-4">
          <label className="flex flex-col gap-1 text-xs sm:col-span-2">
            <span className="text-(--color-muted)">E-mail</span>
            <Input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="nome@instituicao.org"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Nome</span>
            <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Papel</span>
            <Select value={role} onChange={(event) => setRole(event.target.value as AuthUser["role"])}>
              {ROLES.map((value) => (
                <option key={value} value={value}>
                  {ROLE_LABEL[value]}
                </option>
              ))}
            </Select>
          </label>
        </div>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-(--color-muted)">Senha temporária</span>
          <Input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
          />
        </label>
        <div className="flex items-center gap-3">
          <Button variant="primary" disabled={!valid || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "Criando…" : "Criar conta"}
          </Button>
          {create.data ? (
            <span className="text-xs text-(--color-ok)">Conta {create.data.email} criada.</span>
          ) : null}
        </div>
        {create.error ? <ErrorState error={create.error} /> : null}
      </div>
    </Disclosure>
  );
}

function UserCard({ user, isSelf, onChanged }: { user: AuthUser; isSelf: boolean; onChanged: () => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(user.name);
  const [role, setRole] = useState(user.role);
  const [password, setPassword] = useState("");
  const [mustChange, setMustChange] = useState(true);

  const refresh = () => {
    onChanged();
    // Renaming the signed-in account changes the name the shell prints and the ledgers record.
    void queryClient.invalidateQueries({ queryKey: ["current-user"] });
    void queryClient.invalidateQueries({ queryKey: ["identity", "users", user.user_id, "sessions"] });
  };

  const save = useMutation({
    mutationFn: (changes: UpdateUserRequest) => updateUser(user.user_id, changes),
    onSuccess: refresh,
  });

  const toggleActive = useMutation({
    mutationFn: () => updateUser(user.user_id, { is_active: !user.is_active }),
    onSuccess: refresh,
  });

  const reset = useMutation({
    mutationFn: () => resetUserPassword(user.user_id, { password, must_change: mustChange }),
    onSuccess: () => {
      setPassword("");
      refresh();
    },
  });

  const dirty = name.trim() !== user.name || role !== user.role;

  return (
    <Disclosure
      open={open}
      onOpenChange={setOpen}
      className={user.is_active ? undefined : "opacity-80"}
      toggleLabel="Editar esta conta"
      header={
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{user.name}</span>
          <span className="text-xs text-(--color-muted)">{user.email}</span>
          <Badge tone="accent">{ROLE_LABEL[user.role]}</Badge>
          {user.is_active ? <Badge tone="ok">ativa</Badge> : <Badge tone="neutral">desativada</Badge>}
          {isSelf ? <Badge tone="neutral">você</Badge> : null}
          {user.must_change_password ? (
            <Badge tone="warn" title="Ainda usa a senha temporária">
              troca pendente
            </Badge>
          ) : null}
          <span className="w-full text-xs text-(--color-muted)">
            último acesso: {user.last_login_at ? formatDateTime(user.last_login_at) : "nunca"}
          </span>
        </div>
      }
      actions={
        <Button
          size="sm"
          variant={user.is_active ? "ghost" : "secondary"}
          disabled={toggleActive.isPending}
          onClick={() => toggleActive.mutate()}
        >
          {user.is_active ? "desativar" : "reativar"}
        </Button>
      }
    >
      <div className="grid gap-4">
        <div className="grid gap-2 sm:grid-cols-3">
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Nome</span>
            <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-(--color-muted)">Papel</span>
            <Select value={role} onChange={(event) => setRole(event.target.value as AuthUser["role"])}>
              {ROLES.map((value) => (
                <option key={value} value={value}>
                  {ROLE_LABEL[value]}
                </option>
              ))}
            </Select>
          </label>
          <div className="flex items-end">
            <Button
              variant="primary"
              disabled={!dirty || save.isPending || name.trim().length === 0}
              onClick={() => save.mutate({ name: name.trim(), role })}
            >
              {save.isPending ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </div>
        {save.error ? <ErrorState error={save.error} /> : null}
        {toggleActive.error ? <ErrorState error={toggleActive.error} /> : null}

        <div className="grid gap-2 border-t border-(--color-line) pt-3">
          <p className="text-xs text-(--color-muted)">
            Redefinir a senha encerra todas as sessões desta conta — é o que se faz quando alguém
            perdeu o acesso.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex min-w-56 flex-1 flex-col gap-1 text-xs">
              <span className="text-(--color-muted)">Nova senha temporária</span>
              <Input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
              />
            </label>
            <label className="flex items-center gap-2 pb-2 text-xs">
              <input
                type="checkbox"
                checked={mustChange}
                onChange={(event) => setMustChange(event.target.checked)}
              />
              <span>exigir troca no próximo acesso</span>
            </label>
            <Button
              variant="secondary"
              disabled={password.length === 0 || reset.isPending}
              onClick={() => reset.mutate()}
            >
              {reset.isPending ? "Redefinindo…" : "Redefinir senha"}
            </Button>
          </div>
          {reset.data ? <p className="text-xs text-(--color-ok)">{routeMessage(reset.data)}</p> : null}
          {reset.error ? <ErrorState error={reset.error} /> : null}
        </div>

        {open ? <SessionList userId={user.user_id} /> : null}
      </div>
    </Disclosure>
  );
}

/**
 * Where one account is signed in, read only while the row is open.
 *
 * The list is the answer to "that session is not me", so each row shows what identifies it — the
 * agent, the address, when it was last used — and the row that is *this* request's own session is
 * marked: ending the session you are using is a decision worth seeing coming.
 */
function SessionList({ userId }: { userId: number }) {
  const queryClient = useQueryClient();
  const sessions = useQuery(queries.userSessions(userId));

  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: ["identity", "users", userId, "sessions"] });

  const revoke = useMutation({
    mutationFn: (sessionId: number) => revokeUserSession(userId, sessionId),
    onSuccess: invalidate,
  });
  const revokeAll = useMutation({
    mutationFn: () => revokeUserSessions(userId),
    onSuccess: invalidate,
  });

  const rows = sessions.data ?? [];

  return (
    <div className="grid gap-2 border-t border-(--color-line) pt-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium">Sessões ativas</p>
        <Button
          size="sm"
          variant="danger"
          disabled={rows.length === 0 || revokeAll.isPending}
          onClick={() => revokeAll.mutate()}
        >
          {revokeAll.isPending ? "Encerrando…" : "Encerrar todas"}
        </Button>
      </div>

      {sessions.isPending ? <Skeleton className="h-10" /> : null}
      {sessions.error ? <ErrorState error={sessions.error} /> : null}
      {!sessions.isPending && rows.length === 0 ? (
        <p className="text-xs text-(--color-muted)">Nenhuma sessão ativa.</p>
      ) : null}

      <ul className="grid gap-1">
        {rows.map((session) => (
          <li
            key={session.session_id}
            className="flex flex-wrap items-center gap-2 rounded-md bg-black/[0.02] px-2 py-1.5 text-xs"
          >
            <span className="min-w-40 flex-1 truncate" title={session.user_agent ?? undefined}>
              {session.user_agent ?? "agente não informado"}
            </span>
            <span className="text-(--color-muted)">{session.ip_address ?? "—"}</span>
            <span className="text-(--color-muted)">vista em {formatDateTime(session.last_seen_at)}</span>
            {session.is_current ? <Badge tone="accent">esta sessão</Badge> : null}
            <Button
              size="sm"
              variant="ghost"
              disabled={revoke.isPending}
              onClick={() => revoke.mutate(session.session_id)}
            >
              encerrar
            </Button>
          </li>
        ))}
      </ul>

      {revoke.error ? <ErrorState error={revoke.error} /> : null}
      {revokeAll.error ? <ErrorState error={revokeAll.error} /> : null}
    </div>
  );
}
