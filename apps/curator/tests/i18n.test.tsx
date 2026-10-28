/**
 * The i18n core: the locale a browser asks for, the catalogue the tree reads, and the formatters.
 *
 * The point of pinning this here is the pair that can drift silently: the typed catalogue is checked
 * by `tsc` for completeness, but not for *which* catalogue a render reads, nor for the locale the
 * plain `format.ts` functions use (they read a module variable the provider keeps in step).
 */

import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { LocaleProvider, useCopy, useLocale } from "../src/i18n/context";
import { detectLocale, setActiveLocale } from "../src/i18n/locale";
import { Trans } from "../src/i18n/trans";
import { descricoes, formatDate } from "../src/lib/format";

afterEach(cleanup);

beforeEach(() => {
  localStorage.clear();
  setActiveLocale("pt-BR");
});

function Probe() {
  const { locale, setLocale } = useLocale();
  const copy = useCopy();

  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="signin">{copy.auth.login.signIn}</span>
      <span data-testid="date">{formatDate("2026-10-27")}</span>
      <span data-testid="count">{descricoes(1)}</span>
      <button type="button" onClick={() => setLocale("en")}>
        en
      </button>
    </div>
  );
}

describe("detectLocale", () => {
  it("reads Portuguese and English, and falls back to the product's language", () => {
    expect(detectLocale("pt-BR")).toBe("pt-BR");
    expect(detectLocale("pt-PT")).toBe("pt-BR");
    expect(detectLocale("en-US")).toBe("en");
    expect(detectLocale("en-GB")).toBe("en");
    expect(detectLocale("de-DE")).toBe("pt-BR");
    expect(detectLocale("")).toBe("pt-BR");
  });
});

describe("the provider", () => {
  it("switches the catalogue, the document language and the formatters together", () => {
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );

    expect(screen.getByTestId("signin").textContent).toBe("Entrar");
    expect(screen.getByTestId("count").textContent).toBe("1 descrição");
    const portugueseDate = screen.getByTestId("date").textContent;
    expect(document.documentElement.lang).toBe("pt-BR");

    fireEvent.click(screen.getByRole("button", { name: "en" }));

    expect(screen.getByTestId("locale").textContent).toBe("en");
    expect(screen.getByTestId("signin").textContent).toBe("Sign in");
    expect(screen.getByTestId("count").textContent).toBe("1 description");
    expect(screen.getByTestId("date").textContent).not.toBe(portugueseDate);
    expect(document.documentElement.lang).toBe("en");
  });
});

describe("Trans", () => {
  it("keeps one sentence and renders the markup a placeholder carries", () => {
    render(
      <Trans
        text="Um administrador redefine a sua senha em {settings}, na conta certa."
        values={{ settings: <strong>Configurações → Usuários</strong> }}
      />,
    );

    const strong = screen.getByText("Configurações → Usuários");
    expect(strong.tagName).toBe("STRONG");
    expect(screen.getByText(/na conta certa/)).toBeTruthy();
  });
});
