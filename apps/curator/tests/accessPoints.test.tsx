/**
 * The access-point chip field (#229).
 *
 * The behaviour that matters: the typed spelling is kept, the catalogue pick is the other path, the
 * chips are never removed or rewritten by the preview, and the summary is one sentence about the
 * whole string. The preview's statuses are the contract's; the screen owns the Portuguese, so the
 * summary here is a plain marker the control renders.
 */

import { afterEach, describe, expect, it } from "bun:test";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";

import type { AccessPointPreviewItem } from "../src/api/client";
import {
  AccessPointsField,
  type AccessPointChip,
  type AccessPointSuggestion,
} from "../src/components/description/AccessPointsField";
import { groupAccessPointPreview } from "../src/lib/taxonomy";

afterEach(cleanup);

const COPY = {
  placeholder: "Busque uma tag ou digite um termo novo",
  add: (term: string) => `Adicionar “${term}”`,
  remove: (name: string) => `Remover ${name}`,
  searching: "Buscando…",
  searchFailed: "Busca falhou",
  duplicate: (term: string) => `“${term}” já está na lista.`,
  previewFailed: "Prévia falhou",
};

function previewItem(
  input: string,
  status: AccessPointPreviewItem["status"],
  name: string | null = null,
  tagId: number | null = null,
): AccessPointPreviewItem {
  return { input, name, status, tag_id: tagId };
}

function describePreview(items: AccessPointPreviewItem[]) {
  if (items.length === 0) return null;
  return <span>{items.map((item) => `${item.status}:${item.name ?? item.input}`).join("|")}</span>;
}

function Harness({
  search = async () => [],
  preview = async () => [],
  describedBy,
  onChange,
}: {
  search?: (term: string) => Promise<AccessPointSuggestion[]>;
  preview?: (indexingPoints: string) => Promise<AccessPointPreviewItem[]>;
  describedBy?: string;
  onChange?: (chips: AccessPointChip[]) => void;
}) {
  const [chips, setChips] = useState<AccessPointChip[]>([]);

  return (
    <AccessPointsField
      id="access-points"
      chips={chips}
      onChange={(next) => {
        setChips(next);
        onChange?.(next);
      }}
      search={search}
      preview={preview}
      describe={describePreview}
      copy={COPY}
      describedBy={describedBy}
      searchDelayMs={0}
      previewDelayMs={0}
    />
  );
}

function addTyped(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } });
  fireEvent.keyDown(input, { key: "Enter" });
}

describe("AccessPointsField", () => {
  it("adds the typed spelling through the explicit option and shows the summary", async () => {
    const preview = async () => [previewItem("Obras", "NEW", "obras")];
    render(<Harness preview={preview} />);

    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "Obras" } });
    expect(screen.getByText("Adicionar “Obras”")).toBeTruthy();

    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByRole("button", { name: "Remover Obras" })).toBeTruthy();
    await screen.findByText("NEW:obras");
  });

  it("adds the catalogue tag when a suggestion is picked", async () => {
    const search = async () => [{ tagId: 7, name: "urbanismo", hint: "5 doc" }];
    const preview = async () => [previewItem("urbanismo", "EXISTING", "urbanismo", 7)];
    render(<Harness search={search} preview={preview} />);

    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "urb" } });

    const option = await screen.findByRole("option", { name: /urbanismo/ });
    fireEvent.click(within(option).getByRole("button"));

    expect(screen.getByRole("button", { name: "Remover urbanismo" })).toBeTruthy();
    expect(screen.queryByText(/Adicionar/)).toBeNull();
  });

  it("adds a pasted list as chips and previews the joined string once", async () => {
    const previewed: string[] = [];
    const preview = async (value: string) => {
      previewed.push(value);
      return value.split(", ").map((name) => previewItem(name, "NEW", name));
    };
    render(<Harness preview={preview} />);

    const input = screen.getByRole("combobox");
    fireEvent.paste(input, { clipboardData: { getData: () => "alfa, beta; gama|delta" } });

    expect(screen.getByRole("button", { name: "Remover alfa" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Remover beta" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Remover gama" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Remover delta" })).toBeTruthy();

    await screen.findByText("NEW:alfa|NEW:beta|NEW:gama|NEW:delta");
    expect(previewed.at(-1)).toBe("alfa, beta, gama, delta");
  });

  it("keeps a blocked term in the chips and explains it in the summary", async () => {
    const preview = async () => [previewItem("obras", "STOPWORD")];
    render(<Harness preview={preview} />);

    const input = screen.getByRole("combobox");
    addTyped(input, "obras");

    expect(screen.getByRole("button", { name: "Remover obras" })).toBeTruthy();
    await screen.findByText("STOPWORD:obras");
  });

  it("does not add the same name twice", async () => {
    render(<Harness />);
    const input = screen.getByRole("combobox");

    addTyped(input, "obras");
    addTyped(input, "Obras");

    expect(screen.getAllByRole("button", { name: "Remover obras" })).toHaveLength(1);
    expect(screen.getByText("“Obras” já está na lista.")).toBeTruthy();
  });

  it("removes the last chip on Backspace in an empty input", async () => {
    render(<Harness />);
    const input = screen.getByRole("combobox");

    addTyped(input, "alfa");
    addTyped(input, "beta");
    fireEvent.keyDown(input, { key: "Backspace" });

    expect(screen.queryByRole("button", { name: "Remover beta" })).toBeNull();
    expect(screen.getByRole("button", { name: "Remover alfa" })).toBeTruthy();
  });

  it("removes one chip with its own button", async () => {
    render(<Harness />);
    const input = screen.getByRole("combobox");

    addTyped(input, "alfa");
    addTyped(input, "beta");
    fireEvent.click(screen.getByRole("button", { name: "Remover alfa" }));

    expect(screen.queryByRole("button", { name: "Remover alfa" })).toBeNull();
    expect(screen.getByRole("button", { name: "Remover beta" })).toBeTruthy();
  });

  it("warns when the preview fails and keeps the typed terms", async () => {
    const preview = async () => {
      throw new Error("offline");
    };
    render(<Harness preview={preview} />);

    const input = screen.getByRole("combobox");
    addTyped(input, "alfa");

    await screen.findByText("Prévia falhou");
    expect(screen.getByRole("button", { name: "Remover alfa" })).toBeTruthy();
  });

  it("still lets the archivist use the term when the type-ahead fails", async () => {
    const search = async () => {
      throw new Error("offline");
    };
    render(<Harness search={search} />);

    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "alfa" } });
    await screen.findByText("Busca falhou");
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.getByRole("button", { name: "Remover alfa" })).toBeTruthy();
  });

  it("exposes the combobox, the listbox and the described hint", async () => {
    const search = async () => [{ tagId: 1, name: "alfa" }];
    render(<Harness search={search} describedBy="access-points-hint" />);

    const input = screen.getByRole("combobox");
    expect(input.getAttribute("aria-autocomplete")).toBe("list");
    expect(input.getAttribute("aria-describedby")).toBe("access-points-hint");

    fireEvent.change(input, { target: { value: "a" } });
    const option = await screen.findByRole("option");
    expect(input.getAttribute("aria-expanded")).toBe("true");
    expect(input.getAttribute("aria-activedescendant")).toBe(option.id);
    expect(screen.getByRole("listbox")).toBeTruthy();
  });
});

describe("groupAccessPointPreview", () => {
  it("groups only the entries the summary has to mention", () => {
    const groups = groupAccessPointPreview([
      previewItem("urbanismo", "EXISTING", "urbanismo", 1),
      previewItem("Urbanismo", "EXISTING", "urbanismo", 1),
      previewItem("urbanismos", "SYNONYM", "urbanismo", 1),
      previewItem("obras", "STOPWORD"),
      previewItem("ab", "TOO_SHORT"),
      previewItem("novo", "NEW", "novo"),
      previewItem("Novo", "DUPLICATE"),
    ]);

    expect(groups.created).toHaveLength(1);
    expect(groups.dropped).toHaveLength(2);
    expect(groups.synonyms).toHaveLength(1);
    expect(groups.respelled).toHaveLength(1);
  });
});
