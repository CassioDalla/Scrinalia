import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { logout, updateLocale, type AuthUser } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { useCopy, useLocale } from "@/i18n/context";
import { detectLocale, LOCALE_LABEL, LOCALES, type Locale } from "@/i18n/locale";
import { cn } from "@/lib/cn";

/**
 * Who is signed in, and the account actions that are not navigation.
 *
 * The rail is not a settings page: identity, session actions and an account preference are three
 * different kinds of thing, and stacking them as peers made **Sair** look like **Trocar senha** and
 * left the language with nowhere to live when the rail collapsed. The footer is therefore one row —
 * identity, then the one action that has to be reachable in a hurry — and everything that changes
 * rarely moves into a popover that opens upward.
 *
 * The popover is deliberately **not** a menu: it holds a button and a `<select>`, and a menu role
 * would promise arrow-key navigation and a menuitem for a control that is not one. It is a
 * non-modal dialog with the DOM's own tab order, and it is absent from the DOM while closed, so a
 * screen reader does not hear controls that cannot be reached.
 *
 * Collapsed, 64px cannot hold a name. The avatar is the trigger and carries the full name, role and
 * address as its accessible name; the popover is where the same identity, the password and the
 * language survive.
 */
export function SessionFooter({
  user,
  collapsed,
  onChangePassword,
}: {
  user: AuthUser;
  collapsed: boolean;
  onChangePassword: () => void;
}) {
  const copy = useCopy();
  const { setLocale } = useLocale();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const container = useRef<HTMLDivElement>(null);
  const popover = useRef<HTMLDivElement>(null);
  const popoverId = useId();

  const identity = `${user.name} · ${copy.roles[user.role]} · ${user.email}`;
  const initial = user.name.trim().slice(0, 1).toUpperCase() || "?";

  const signOut = useMutation({
    mutationFn: logout,
    // Whether the API answered or the session was already over, this browser is signed out: clearing
    // the cached account is what draws the sign-in form.
    onSettled: () => queryClient.setQueryData(["current-user"], null),
  });
  const saveLocale = useMutation({
    mutationFn: (next: Locale | null) => updateLocale(next),
    onSuccess: (account) => {
      queryClient.setQueryData(["current-user"], account);
      setLocale(account.locale ?? detectLocale(), { persist: false });
    },
  });

  /*
    Focus moves into the popover on open, and Escape returns it to the trigger. Without the first
    half a keyboard would keep walking the rail behind an open panel; without the second it would
    fall to the document body and the next Tab would start from the top of the page.
  */
  useEffect(() => {
    if (!open) return;
    popover.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      trigger.current?.focus();
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (container.current?.contains(target)) return;
      setOpen(false);
    };

    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open]);

  const close = () => setOpen(false);

  const signOutControl = (
    <SignOut
      pending={signOut.isPending}
      label={copy.shell.signOut}
      pendingLabel={copy.shell.signingOut}
      onSignOut={() => signOut.mutate()}
    />
  );

  return (
    <div
      ref={container}
      className={cn(
        "relative shrink-0 border-t border-(--color-rail-line)",
        collapsed ? "flex flex-col items-center gap-2 px-1.5 py-3" : "px-4 py-3",
      )}
    >
      {collapsed ? (
        <>
          <button
            ref={trigger}
            type="button"
            aria-expanded={open}
            aria-controls={popoverId}
            aria-haspopup="dialog"
            aria-label={identity}
            title={identity}
            onClick={() => setOpen((current) => !current)}
            className="grid size-8 place-items-center rounded-full bg-(--color-rail-active) text-xs font-semibold text-(--color-rail-ink) transition hover:bg-(--color-rail-hover)"
          >
            <span aria-hidden>{initial}</span>
          </button>
          {signOutControl}
        </>
      ) : (
        <div className="flex items-center gap-1">
          <button
            ref={trigger}
            type="button"
            aria-expanded={open}
            aria-controls={popoverId}
            aria-haspopup="dialog"
            onClick={() => setOpen((current) => !current)}
            className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 text-left transition hover:bg-(--color-rail-hover)"
          >
            <span
              aria-hidden
              className="grid size-8 shrink-0 place-items-center rounded-full bg-(--color-rail-active) text-xs font-semibold text-(--color-rail-ink)"
            >
              {initial}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-(--color-rail-ink)">{user.name}</span>
              <span className="block truncate text-xs text-(--color-rail-muted)">{copy.roles[user.role]}</span>
            </span>
          </button>
          {signOutControl}
        </div>
      )}

      {open ? (
        <div
          ref={popover}
          id={popoverId}
          role="dialog"
          aria-label={copy.shell.account}
          className={cn(
            "absolute bottom-full z-50 mb-2 rounded-lg bg-(--color-surface) p-3 text-(--color-ink) shadow-xl ring-1 ring-(--color-line)",
            collapsed ? "left-2 w-72" : "left-2 right-2",
          )}
        >
          <p className="break-words text-sm text-(--color-muted)">{user.email}</p>
          <div className="my-2 border-t border-(--color-line)" />
          <button
            type="button"
            data-autofocus
            onClick={() => {
              close();
              onChangePassword();
            }}
            className="w-full rounded px-1 py-1 text-left text-sm text-(--color-ink) transition hover:bg-black/[0.04]"
          >
            {copy.shell.changePassword}
          </button>
          <label className="mt-1 flex items-center gap-2 text-xs text-(--color-muted)">
            <span className="shrink-0">{copy.shell.language}</span>
            <select
              value={user.locale ?? "auto"}
              disabled={saveLocale.isPending}
              onChange={(event) => {
                const value = event.target.value;
                saveLocale.mutate(value === "auto" ? null : (value as Locale));
              }}
              className="min-w-0 flex-1 rounded border border-(--color-line) bg-(--color-surface) px-1 py-0.5 text-xs text-(--color-ink)"
            >
              <option value="auto">{copy.shell.automatic}</option>
              {LOCALES.map((value) => (
                <option key={value} value={value}>
                  {LOCALE_LABEL[value]}
                </option>
              ))}
            </select>
          </label>
          {saveLocale.isError ? (
            <p className="pt-1 text-xs text-(--color-danger)">{copy.shell.localeFailed}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * The one action that has to be reachable in a hurry, in both rail states.
 *
 * It is an icon-only control because the rail is a navigation column and the word would compete
 * with the menu; the accessible name and the tooltip are what keep it legible. The pending state is
 * the same label the words version used, so a slow sign-out never looks like a dead button.
 */
function SignOut({
  pending,
  label,
  pendingLabel,
  onSignOut,
}: {
  pending: boolean;
  label: string;
  pendingLabel: string;
  onSignOut: () => void;
}) {
  const text = pending ? pendingLabel : label;

  return (
    <Button
      variant="ghost"
      size="sm"
      className="size-8 shrink-0 px-0 text-(--color-rail-muted) hover:bg-(--color-rail-hover) hover:text-(--color-rail-ink)"
      title={text}
      aria-label={text}
      disabled={pending}
      onClick={onSignOut}
    >
      <LogOut className="size-4" aria-hidden />
    </Button>
  );
}
