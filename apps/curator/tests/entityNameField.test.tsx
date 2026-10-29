/**
 * The producer autocomplete (#230).
 *
 * The behaviour that matters: picking a suggestion copies the catalogue's name and **not** its id,
 * the copy is verbatim, only the fragment around the caret is replaced (so the archivist's own
 * separators survive), and a name the catalogue does not have stays typeable. The list is a
 * suggestion, never a gate.
 */

import { afterEach, describe, expect, it } from "bun:test";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";

import type { EntityRelevance } from "../src/api/client";
import { EntityNameField, segmentAt } from "../src/components/description/EntityNameField";
import { LocaleProvider } from "../src/i18n/context";
import { setActiveLocale } from "../src/i18n/locale";

// The catalogue's Portuguese is the product's voice; a test asserting the sentences pins that one.
setActiveLocale("pt-BR", false);
afterEach(cleanup);

const PREF: EntityRelevance = {
  entity_id: 7,
  name: "prefeitura municipal de curitiba",
  entity_type: "ORG",
  total_usage: 73,
};

const GUIDO: EntityRelevance = {
  entity_id: 9,
  name: "guido ghilardi",
  entity_type: "PER",
  total_usage: 1,
};

function Harness({
  initial = "",
  search = async () => [],
  onChange,
}: {
  initial?: string;
  search?: (term: string) => Promise<EntityRelevance[]>;
  onChange?: (value: string) => void;
}) {
  const [value, setValue] = useState(initial);

  return (
    <LocaleProvider>
      <EntityNameField
        id="producers"
        value={value}
        search={search}
        searchDelayMs={0}
        onChange={(next) => {
          setValue(next);
          onChange?.(next);
        }}
      />
    </LocaleProvider>
  );
}

describe("EntityNameField", () => {
  it("inserts the catalogue name and never the id", async () => {
    const written: string[] = [];
    render(<Harness search={async () => [PREF]} onChange={(value) => written.push(value)} />);

    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "pref" } });

    const option = await screen.findByRole("option", { name: /prefeitura/ });
    fireEvent.click(within(option).getByRole("button"));

    expect((input as HTMLInputElement).value).toBe(PREF.name);
    // Every keystroke is a change of the field; the pick is the last one, and it carries no id.
    expect(written).toEqual(["pref", PREF.name]);
    expect((input as HTMLInputElement).value).not.toContain(String(PREF.entity_id));
  });

  it("copies the name verbatim, without re-casing what the catalogue stores", async () => {
    render(<Harness search={async () => [PREF]} />);

    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "prefeitura" } });
    await screen.findByRole("option", { name: /prefeitura/ });
    fireEvent.keyDown(input, { key: "Enter" });

    expect((input as HTMLInputElement).value).toBe("prefeitura municipal de curitiba");
  });

  it("replaces only the fragment at the caret, keeping the archivist's separators", async () => {
    const search = async (term: string) => (term === "gui" ? [GUIDO] : []);
    render(<Harness initial="câmara municipal de curitiba, " search={search} />);

    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "câmara municipal de curitiba, gui" } });

    const option = await screen.findByRole("option", { name: /guido/ });
    fireEvent.click(within(option).getByRole("button"));

    expect((input as HTMLInputElement).value).toBe("câmara municipal de curitiba, guido ghilardi");
  });

  it("searches the fragment, not the whole field", async () => {
    const terms: string[] = [];
    const search = async (term: string) => {
      terms.push(term);
      return [GUIDO];
    };
    render(<Harness initial="câmara municipal de curitiba, " search={search} />);

    const input = screen.getByRole("combobox");
    input.setSelectionRange((input as HTMLInputElement).value.length, (input as HTMLInputElement).value.length);
    fireEvent.change(input, { target: { value: "câmara municipal de curitiba, gui" } });

    await screen.findByRole("option", { name: /guido/ });
    expect(terms.at(-1)).toBe("gui");
  });

  it("keeps a term the catalogue does not have", async () => {
    const written: string[] = [];
    render(<Harness search={async () => []} onChange={(value) => written.push(value)} />);

    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "fazenda experimental" } });

    await screen.findByText("Nenhuma entidade com esse trecho");
    expect((input as HTMLInputElement).value).toBe("fazenda experimental");
    expect(written.at(-1)).toBe("fazenda experimental");
  });

  it("shows the entity type and the number of descriptions", async () => {
    render(<Harness search={async () => [PREF]} />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "pref" } });
    const option = await screen.findByRole("option", { name: /prefeitura/ });

    expect(option.textContent).toContain("ORG");
    expect(option.textContent).toContain("73");
  });

  it("says so when the search fails and still lets the archivist type", async () => {
    render(
      <Harness
        search={async () => {
          throw new Error("offline");
        }}
      />,
    );

    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "igreja" } });

    await screen.findByText("Não foi possível buscar as entidades agora.");
    expect((input as HTMLInputElement).value).toBe("igreja");
  });

  it("exposes the combobox, the listbox and the described hint", async () => {
    render(<Harness search={async () => [PREF, GUIDO]} />);

    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "e" } });

    const option = await screen.findByRole("option", { name: /prefeitura/ });
    expect(input.getAttribute("aria-autocomplete")).toBe("list");
    expect(input.getAttribute("aria-expanded")).toBe("true");
    expect(input.getAttribute("aria-activedescendant")).toBe(option.id);
    expect(screen.getByRole("listbox")).toBeTruthy();
  });
});

describe("segmentAt", () => {
  it("returns the whole text when there is no separator", () => {
    expect(segmentAt("prefeitura municipal", 9).term).toBe("prefeitura municipal");
  });

  it("bounds the fragment by the separators and trims the spaces", () => {
    const text = "câmara municipal, guido ghilardi; outra";
    const segment = segmentAt(text, 22);

    expect(segment.term).toBe("guido ghilardi");
    expect(text.slice(0, segment.start)).toBe("câmara municipal, ");
    expect(text.slice(segment.end)).toBe("; outra");
  });

  it("keeps a fragment that only has spaces empty", () => {
    expect(segmentAt("alfa,  , beta", 6).term).toBe("");
  });
});
