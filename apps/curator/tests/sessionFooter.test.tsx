/**
 * The session footer (#262).
 *
 * The rail's foot used to be four bands of peers: identity, two text buttons and a `<select>`. The
 * defect this pins is the hierarchy — one account trigger, one sign-out icon, and the preferences
 * inside a popover that works in both rail widths. The behaviour is what matters: open and close,
 * focus returning to the trigger, the language mutation (including `null` for *Automático* and the
 * failure message inside the popover), and sign-out.
 *
 * The API client is mocked at the module seam: `createClient` captures `globalThis.fetch` when the
 * module loads, so a fetch stub installed by a test arrives too late. `logout` and `updateLocale`
 * are the only calls this component makes.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterAll, afterEach, beforeEach, describe, expect, it, mock } from "bun:test";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type { AuthUser } from "../src/api/client";
import { LocaleProvider } from "../src/i18n/context";
import { setActiveLocale, type Locale } from "../src/i18n/locale";

const USER: AuthUser = {
  user_id: 7,
  name: "Ana",
  email: "ana@instituicao.br",
  role: "CURATOR",
  is_active: true,
  is_locked: false,
  must_change_password: false,
  failed_attempts: 0,
  locale: null,
};

let saves: (Locale | null)[] = [];
let logouts = 0;
let failLocale = false;
let holdLogout = false;
let releaseLogout: (() => void) | null = null;

const updateLocaleMock = mock(async (locale: Locale | null) => {
  if (failLocale) throw new Error("the API refused the language");
  saves.push(locale);
  return { ...USER, locale };
});
const logoutMock = mock(async () => {
  logouts += 1;
  if (holdLogout) {
    await new Promise<void>((resolve) => {
      releaseLogout = resolve;
    });
  }
  return { code: "SESSION_ENDED" as const, message: "Sessão encerrada." };
});

mock.module("../src/api/client", () => ({
  logout: logoutMock,
  updateLocale: updateLocaleMock,
}));

const { SessionFooter } = await import("../src/components/layout/SessionFooter");

let client: QueryClient;

beforeEach(() => {
  localStorage.clear();
  setActiveLocale("pt-BR");
  saves = [];
  logouts = 0;
  failLocale = false;
  holdLogout = false;
  releaseLogout = null;
  client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
});

afterEach(cleanup);

afterAll(() => mock.restore());

function renderFooter({ collapsed = false, user = USER }: { collapsed?: boolean; user?: AuthUser } = {}) {
  const onChangePassword = () => {};
  const result = render(
    <QueryClientProvider client={client}>
      <LocaleProvider>
        <SessionFooter user={user} collapsed={collapsed} onChangePassword={onChangePassword} />
      </LocaleProvider>
    </QueryClientProvider>,
  );
  return { ...result, onChangePassword };
}

function expandedTrigger(): HTMLElement {
  return screen.getByRole("button", { name: "Ana Curador" });
}

function collapsedTrigger(): HTMLElement {
  return screen.getByRole("button", { name: "Ana · Curador · ana@instituicao.br" });
}

function dialog(): HTMLElement {
  return screen.getByRole("dialog", { name: "Conta" });
}

describe("the session footer", () => {
  it("keeps name and role visible, and puts the email in the account popover", () => {
    renderFooter();

    const trigger = expandedTrigger();
    expect(screen.getByText("Ana")).toBeTruthy();
    expect(screen.getByText("Curador")).toBeTruthy();
    expect(screen.queryByText(USER.email)).toBeNull();
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(trigger.getAttribute("aria-controls")).toBeTruthy();

    fireEvent.click(trigger);

    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(within(dialog()).getByText(USER.email)).toBeTruthy();
    expect(within(dialog()).getByRole("button", { name: "Trocar senha" })).toBeTruthy();
    expect(within(dialog()).getByRole("combobox", { name: "Idioma" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sair" })).toBeTruthy();
  });

  it("opens on the password action, closes on Escape and returns focus to the trigger", () => {
    renderFooter();
    const trigger = expandedTrigger();

    fireEvent.click(trigger);
    const password = within(dialog()).getByRole("button", { name: "Trocar senha" });
    expect(document.activeElement).toBe(password);

    fireEvent.keyDown(document.activeElement ?? document, { key: "Escape" });

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(trigger);
  });

  it("closes on a click outside the account area", () => {
    renderFooter();
    fireEvent.click(expandedTrigger());
    expect(screen.getByRole("dialog")).toBeTruthy();

    fireEvent.pointerDown(document.body);

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens the password route and closes the popover", () => {
    let navigated = false;
    render(
      <QueryClientProvider client={client}>
        <LocaleProvider>
          <SessionFooter user={USER} collapsed={false} onChangePassword={() => (navigated = true)} />
        </LocaleProvider>
      </QueryClientProvider>,
    );

    fireEvent.click(expandedTrigger());
    fireEvent.click(within(dialog()).getByRole("button", { name: "Trocar senha" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(navigated).toBe(true);
  });

  it("saves a chosen language and switches the catalogue without reloading", async () => {
    renderFooter();
    fireEvent.click(expandedTrigger());

    fireEvent.change(within(dialog()).getByRole("combobox", { name: "Idioma" }), {
      target: { value: "en" },
    });

    await waitFor(() => expect(saves).toEqual(["en"]));
    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: "Account" })).toBeTruthy();
      expect(screen.getByRole("button", { name: "Change password" })).toBeTruthy();
    });
  });

  it("stores Automático as the absence of a choice", async () => {
    renderFooter({ user: { ...USER, locale: "pt-BR" } });
    fireEvent.click(expandedTrigger());

    fireEvent.change(within(dialog()).getByRole("combobox", { name: "Idioma" }), {
      target: { value: "auto" },
    });

    await waitFor(() => expect(saves).toEqual([null]));
  });

  it("shows the language failure inside the popover", async () => {
    failLocale = true;
    renderFooter();
    fireEvent.click(expandedTrigger());

    fireEvent.change(within(dialog()).getByRole("combobox", { name: "Idioma" }), {
      target: { value: "en" },
    });

    expect(await screen.findByText("Não foi possível salvar o idioma.")).toBeTruthy();
    expect(within(dialog()).getByText("Não foi possível salvar o idioma.")).toBeTruthy();
  });

  it("signs out and clears the cached account", async () => {
    renderFooter();

    fireEvent.click(screen.getByRole("button", { name: "Sair" }));

    await waitFor(() => expect(logouts).toBe(1));
    await waitFor(() => expect(client.getQueryData(["current-user"])).toBeNull());
  });

  it("keeps the sign-out pending state legible", async () => {
    holdLogout = true;
    renderFooter();

    fireEvent.click(screen.getByRole("button", { name: "Sair" }));

    await waitFor(() => {
      const pending = screen.getByRole("button", { name: "Saindo…" }) as HTMLButtonElement;
      expect(pending.disabled).toBe(true);
      expect(pending.title).toBe("Saindo…");
    });

    releaseLogout?.();
    await waitFor(() => expect(logouts).toBe(1));
  });

  it("collapsed, the avatar is the trigger and the password lives only in the popover", () => {
    renderFooter({ collapsed: true });

    const trigger = collapsedTrigger();
    expect(trigger.getAttribute("title")).toBe("Ana · Curador · ana@instituicao.br");
    expect(screen.getByRole("button", { name: "Sair" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Trocar senha" })).toBeNull();

    fireEvent.click(trigger);

    const panel = dialog();
    expect(within(panel).getByText(USER.email)).toBeTruthy();
    expect(within(panel).getByRole("button", { name: "Trocar senha" })).toBeTruthy();
    expect(within(panel).getByRole("combobox", { name: "Idioma" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Trocar senha" })).toBeTruthy();
  });
});
