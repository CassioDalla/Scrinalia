/**
 * The diffusion channels page (#213): the generic renderer and the two capability branches.
 *
 * The page has one renderer over `config_fields` on purpose, so the test pins the invariant that
 * makes it worth having: **one control per declared field**, including the boolean the public site
 * turns off. The two conversions are pinned beside it because both fail silently against the API:
 * an empty optional text becomes `null` (an empty `logo_url` is not an `HttpUrl`, and the save would
 * answer 422), and `false` is sent instead of dropped (dropping `allow_indexing` would re-enable
 * the default).
 *
 * The export branch is rendered from a synthetic DTO: no export channel ships yet (#214), and the
 * card has to be ready for the day one does — including the decision that it offers no enqueue
 * action until the run ledger has a channel axis (#212), because a button with no route behind it
 * answers nothing.
 */

import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";

import type { DiffusionChannel, DiffusionConfigField } from "../src/api/client";
import { AddDiffusionChannelPanel } from "../src/components/diffusion/AddDiffusionChannelPanel";
import {
  configSummary,
  configValues,
  missingRequired,
} from "../src/components/diffusion/DiffusionConfigForm";
import { DiffusionChannelCard } from "../src/components/diffusion/DiffusionChannelCard";
import { LocaleProvider } from "../src/i18n/context";
import { setActiveLocale } from "../src/i18n/locale";

const FIELDS: DiffusionConfigField[] = [
  { name: "site_title", label: "Título do site", help: "O nome do site.", kind: "text", required: true },
  { name: "logo_url", label: "URL do logotipo", help: "Um endereço externo.", kind: "text", required: false },
  {
    name: "allow_indexing",
    label: "Permitir indexação",
    help: "Se os buscadores podem indexar.",
    kind: "boolean",
    required: false,
    default: true,
  },
];

const PUBLIC_SITE: DiffusionChannel = {
  code: "public_site",
  label: "Site público",
  description: "O site público embutido.",
  capability: "LIVE",
  configured: true,
  enabled: true,
  config: { site_title: "Acervo", allow_indexing: false, public_base_url: "https://acervo.example.org" },
  config_fields: FIELDS,
  options: {},
  schedule: null,
  last_run_id: null,
  active_run_id: null,
};

const UNCONFIGURED: DiffusionChannel = {
  ...PUBLIC_SITE,
  configured: false,
  enabled: false,
  config: {},
};

const DATASET: DiffusionChannel = {
  code: "dataset",
  label: "Conjunto de dados",
  description: "Um pacote aberto do acervo publicado.",
  capability: "EXPORT",
  configured: true,
  enabled: true,
  config: { destination: "s3://acervo/aberto" },
  config_fields: [
    { name: "destination", label: "Destino", help: "Onde o pacote é escrito.", kind: "text", required: true },
  ],
  options: {},
  schedule: { cron: "0 2 * * *", timezone: "America/Sao_Paulo", next_run_at: "2026-10-30T05:00:00Z" },
  last_run_id: null,
  active_run_id: null,
};

beforeEach(() => {
  localStorage.clear();
  setActiveLocale("pt-BR");
});

afterEach(cleanup);

function withClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LocaleProvider>{node}</LocaleProvider>
    </QueryClientProvider>,
  );
}

describe("the generic configuration renderer", () => {
  it("renders one control per declared field, and the required one says so", () => {
    withClient(<DiffusionChannelCard channel={PUBLIC_SITE} canOperate />);
    fireEvent.click(screen.getByRole("button", { name: /Editar configuração/ }));

    expect(screen.getByLabelText(/Título do site/)).toBeTruthy();
    expect(screen.getByLabelText(/URL do logotipo/)).toBeTruthy();
    expect(screen.getByLabelText(/Permitir indexação/)).toBeTruthy();
    expect(screen.getByText(/obrigatório/)).toBeTruthy();
  });

  it("sends an empty optional text as null and keeps false", () => {
    expect(
      configValues(FIELDS, { site_title: "  Acervo ", logo_url: "   ", allow_indexing: false }),
    ).toEqual({ site_title: "Acervo", logo_url: null, allow_indexing: false });
  });

  it("disables the save while a required field is empty", () => {
    expect(missingRequired(FIELDS, { site_title: " ", allow_indexing: true })).toBe(true);
    expect(missingRequired(FIELDS, { site_title: "Acervo", allow_indexing: true })).toBe(false);
  });

  it("summarises the effective configuration, booleans as sim/não", () => {
    const summary = configSummary(PUBLIC_SITE);

    expect(summary).toContain("Título do site: Acervo");
    expect(summary).toContain("Permitir indexação: não");
    expect(summary).not.toContain("URL do logotipo");
  });
});

describe("the public site card", () => {
  it("links to the configured address only while the channel is enabled", () => {
    const { unmount } = withClient(<DiffusionChannelCard channel={PUBLIC_SITE} canOperate />);
    expect(screen.getByRole("link", { name: "Ver site" }).getAttribute("href")).toBe(
      "https://acervo.example.org",
    );
    unmount();

    withClient(<DiffusionChannelCard channel={{ ...PUBLIC_SITE, enabled: false }} canOperate />);
    expect(screen.queryByRole("link", { name: "Ver site" })).toBeNull();
  });

  it("does not invent an address when none is configured", () => {
    withClient(
      <DiffusionChannelCard
        channel={{ ...PUBLIC_SITE, config: { site_title: "Acervo", allow_indexing: true } }}
        canOperate
      />,
    );
    expect(screen.queryByRole("link", { name: "Ver site" })).toBeNull();
  });

  it("hides every write from an account without OPERATE", () => {
    withClient(<DiffusionChannelCard channel={PUBLIC_SITE} canOperate={false} />);

    expect(screen.queryByRole("button", { name: /Editar configuração/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Desativar/ })).toBeNull();
    expect(screen.getByText(/ficam com o operador/)).toBeTruthy();
  });
});

describe("the export card", () => {
  it("offers the agenda and the last run, and no site link", () => {
    withClient(<DiffusionChannelCard channel={DATASET} canOperate />);

    expect(screen.getByText(/Agenda: America\/Sao_Paulo/)).toBeTruthy();
    expect(screen.getByText(/Última execução: nenhuma/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Ver site" })).toBeNull();
    expect(screen.queryByText(/aplicativo separado/)).toBeNull();
  });

  it("opens the agenda form, and offers no enqueue until the ledger has the channel axis", () => {
    withClient(<DiffusionChannelCard channel={DATASET} canOperate />);

    fireEvent.click(screen.getByRole("button", { name: /Agenda/ }));

    expect(screen.getByDisplayValue("0 2 * * *")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Enfileirar execução/ })).toBeNull();
  });
});

describe("the add picker", () => {
  it("offers only what is not configured, then the generic form", () => {
    withClient(<AddDiffusionChannelPanel available={[UNCONFIGURED]} onClose={() => undefined} />);

    expect(screen.getByText("Site público")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Adicionar" }));

    expect(screen.getByLabelText(/Título do site/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Adicionar" })).toBeTruthy();
  });

  it("says so when every definition already has a row", () => {
    withClient(<AddDiffusionChannelPanel available={[]} onClose={() => undefined} />);

    expect(screen.getByText(/Todos os canais disponíveis já estão configurados/)).toBeTruthy();
  });
});
