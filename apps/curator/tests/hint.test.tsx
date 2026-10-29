/**
 * The one hint primitive (#208).
 *
 * The behavior is the point: a tooltip that only appears on hover is the defect this component
 * replaced, so hover, focus, click/tap, Escape and an outside pointer are pinned here. The text is
 * also asserted to stay in the DOM while closed, because `aria-describedby` pointing at nothing is
 * the same inaccessible tooltip with more markup.
 */

import { afterEach, describe, expect, it } from "bun:test";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

import { Field } from "../src/components/ui/Field";
import { Hint } from "../src/components/ui/Hint";

afterEach(cleanup);

function state(): string | null {
  return screen.getByRole("tooltip").getAttribute("data-state");
}

function trigger(): HTMLElement {
  return screen.getByRole("button", { name: "Sobre o limiar" });
}

function wrapper(): HTMLElement {
  const parent = trigger().parentElement;
  if (!parent) throw new Error("the hint trigger has no wrapper");
  return parent;
}

describe("Hint", () => {
  it("describes the trigger and keeps the text in the DOM while closed", () => {
    render(<Hint label="Sobre o limiar">Abaixo de 0,5 a lista fica vazia.</Hint>);

    const tooltip = screen.getByRole("tooltip");
    expect(trigger().getAttribute("aria-describedby")).toBe(tooltip.id);
    expect(tooltip.textContent).toContain("Abaixo de 0,5");
    expect(tooltip.getAttribute("data-state")).toBe("closed");
  });

  it("opens on hover and closes when the pointer leaves", () => {
    render(<Hint label="Sobre o limiar">Explicação</Hint>);

    fireEvent.mouseOver(wrapper());
    expect(state()).toBe("open");

    fireEvent.mouseOut(wrapper(), { relatedTarget: document.body });
    expect(state()).toBe("closed");
  });

  it("opens on focus, and Escape closes it with the focus still on the trigger", () => {
    render(<Hint label="Sobre o limiar">Explicação</Hint>);
    const button = trigger();
    act(() => button.focus());
    expect(state()).toBe("open");

    fireEvent.keyDown(button, { key: "Escape" });
    expect(state()).toBe("closed");
    expect(document.activeElement).toBe(button);
  });

  it("toggles on click and closes on an outside pointer", () => {
    render(<Hint label="Sobre o limiar">Explicação</Hint>);

    fireEvent.click(trigger());
    expect(state()).toBe("open");

    fireEvent.pointerDown(document.body);
    expect(state()).toBe("closed");
  });

  it("uses the child as the trigger with asChild, as a tab does", () => {
    render(
      <Hint asChild text="O que a varredura ao vivo encontra">
        <button role="tab">Pendentes</button>
      </Hint>,
    );

    const tab = screen.getByRole("tab", { name: "Pendentes" });
    expect(tab.getAttribute("aria-describedby")).toBe(screen.getByRole("tooltip").id);
    expect(tab.getAttribute("title")).toBeNull();
  });

  it("renders the Field info outside the label, so the input's name stays clean", () => {
    render(
      <Field
        label="Limiar de similaridade"
        info={<Hint label="Sobre o limiar">Explicação</Hint>}
      >
        <input />
      </Field>,
    );

    expect(screen.getByLabelText("Limiar de similaridade").tagName).toBe("INPUT");
    expect(trigger().closest("label")).toBeNull();
  });
});
