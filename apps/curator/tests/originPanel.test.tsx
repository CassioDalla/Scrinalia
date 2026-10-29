/**
 * An action that reveals a panel also reveals the card (#234).
 *
 * The defect was a state split in two: the action row set `panel`, but the body that reads it exists
 * only while the card is open, and every card starts collapsed. The click armed a form nothing on
 * screen could show, so the button read as dead — and the form was waiting, unasked, for whoever
 * expanded the card later.
 *
 * `OriginCard` mounts queries and mutations, so what is pinned here is the unit the card composes:
 * the state hook, the action row and the region, inside the real `Disclosure`. That is also the unit
 * the next action added to the row inherits, which is why the state rule lives in the hook and not in
 * a callback inside the card.
 */

import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useId } from "react";

import {
  OriginPanelActions,
  OriginPanelRegion,
  useOriginPanel,
} from "../src/components/ingestion/OriginPanel";
import { Disclosure } from "../src/components/ui/Disclosure";
import { LocaleProvider } from "../src/i18n/context";
import { setActiveLocale } from "../src/i18n/locale";

/** happy-dom has no layout, and no `scrollIntoView` at all; the assertion is that it was asked. */
let scrolled: Element[] = [];

beforeEach(() => {
  localStorage.clear();
  setActiveLocale("pt-BR");
  scrolled = [];
  Element.prototype.scrollIntoView = function (this: Element) {
    scrolled.push(this);
  };
});

afterEach(cleanup);

function Card() {
  const { open, panel, reveal, onOpenChange } = useOriginPanel();
  const configId = useId();
  const scheduleId = useId();

  return (
    <Disclosure
      open={open}
      onOpenChange={onOpenChange}
      header={<span>Acervo</span>}
      actions={
        <OriginPanelActions panel={panel} onSelect={reveal} configId={configId} scheduleId={scheduleId} />
      }
      toggleLabel="Ver fila, execução e configuração"
    >
      <p>Fila</p>
      <OriginPanelRegion
        panel={panel}
        configId={configId}
        scheduleId={scheduleId}
        config={<p>Formulário de configuração</p>}
        schedule={<p>Formulário de agenda</p>}
      />
    </Disclosure>
  );
}

function renderCard() {
  render(
    <LocaleProvider>
      <Card />
    </LocaleProvider>,
  );
}

const configureButton = () => screen.getByRole("button", { name: "Configurar" });
const scheduleButton = () => screen.getByRole("button", { name: "Agenda" });
const cardToggle = () => screen.getByRole("button", { name: "Acervo" });
const configForm = () => screen.queryByText("Formulário de configuração");
const scheduleForm = () => screen.queryByText("Formulário de agenda");

describe("the origin card's panel actions", () => {
  it("opens the collapsed card and the panel in one click", () => {
    renderCard();

    expect(cardToggle().getAttribute("aria-expanded")).toBe("false");
    expect(configForm()).toBeNull();

    fireEvent.click(configureButton());

    expect(cardToggle().getAttribute("aria-expanded")).toBe("true");
    expect(configForm()).not.toBeNull();
  });

  it("brings the panel into view, which is what makes the click move the screen", () => {
    renderCard();
    fireEvent.click(configureButton());

    expect(scrolled).toHaveLength(1);
    expect(scrolled[0]?.textContent).toContain("Formulário de configuração");
    expect(scrolled[0]?.id).toBe(configureButton().getAttribute("aria-controls"));
  });

  it("closes the panel on a second click and leaves the card open", () => {
    renderCard();
    fireEvent.click(configureButton());
    fireEvent.click(configureButton());

    expect(configForm()).toBeNull();
    expect(cardToggle().getAttribute("aria-expanded")).toBe("true");
    expect(scrolled).toHaveLength(1);
  });

  it("shows one panel at a time, and the card stays open when the panel changes", () => {
    renderCard();
    fireEvent.click(configureButton());
    fireEvent.click(scheduleButton());

    expect(configForm()).toBeNull();
    expect(scheduleForm()).not.toBeNull();
    expect(cardToggle().getAttribute("aria-expanded")).toBe("true");
  });

  it("opens the schedule form directly from a collapsed card", () => {
    renderCard();
    fireEvent.click(scheduleButton());

    expect(scheduleForm()).not.toBeNull();
    expect(configForm()).toBeNull();
    expect(cardToggle().getAttribute("aria-expanded")).toBe("true");
  });

  it("names the panel each button owns, and only while that panel exists", () => {
    renderCard();

    expect(configureButton().getAttribute("aria-expanded")).toBe("false");
    expect(configureButton().getAttribute("aria-controls")).toBeNull();

    fireEvent.click(configureButton());

    const controls = configureButton().getAttribute("aria-controls");
    expect(controls).not.toBeNull();
    expect(document.getElementById(controls ?? "")?.textContent).toContain("Formulário de configuração");

    expect(configureButton().getAttribute("aria-expanded")).toBe("true");
    expect(scheduleButton().getAttribute("aria-expanded")).toBe("false");
    expect(scheduleButton().getAttribute("aria-controls")).toBeNull();
  });

  it("resets the panel when the card closes, so reopening shows the facts only", () => {
    renderCard();
    fireEvent.click(configureButton());

    fireEvent.click(cardToggle());
    expect(configForm()).toBeNull();
    expect(cardToggle().getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(cardToggle());
    expect(cardToggle().getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Fila")).toBeTruthy();
    expect(configForm()).toBeNull();
    expect(scheduleForm()).toBeNull();
  });
});
