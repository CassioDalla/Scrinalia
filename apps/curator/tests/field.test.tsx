/**
 * The labelled field, in its two shapes.
 *
 * A simple control keeps the label wrapping it, which is what every screen already relies on. A
 * composite control — the access-point chips, whose remove buttons must not live inside a label —
 * asks for `htmlFor`, and then the label is a sibling pointing at the control's input by id.
 */

import { afterEach, describe, expect, it } from "bun:test";
import { cleanup, render, screen } from "@testing-library/react";

import { Field } from "../src/components/ui/Field";

afterEach(cleanup);

describe("Field", () => {
  it("wraps a simple control in its label", () => {
    render(
      <Field label="Título">
        <input aria-label="título" />
      </Field>,
    );

    const label = screen.getByText("Título").closest("label");
    expect(label).not.toBeNull();
    expect(label?.contains(screen.getByRole("textbox"))).toBe(true);
  });

  it("points at the control by id when htmlFor is given", () => {
    render(
      <Field label="Título" htmlFor="title-input">
        <input id="title-input" />
      </Field>,
    );

    const input = screen.getByLabelText("Título");
    const label = screen.getByText("Título").closest("label");

    expect(label?.getAttribute("for")).toBe("title-input");
    expect(label?.contains(input)).toBe(false);
  });

  it("names the visible hint so the control can describe itself", () => {
    render(
      <Field label="Título" htmlFor="title-input" hint="Explique o título" hintId="title-hint">
        <input id="title-input" aria-describedby="title-hint" />
      </Field>,
    );

    expect(screen.getByText("Explique o título").id).toBe("title-hint");
    expect(screen.getByLabelText("Título").getAttribute("aria-describedby")).toBe("title-hint");
  });
});
