import { Fragment, type ReactNode } from "react";

/**
 * A message with `{name}` placeholders, rendered with the markup each one carries.
 *
 * The alternative — splitting a sentence around an element in the screen — freezes the word order
 * into the component, which is the thing a translation cannot have. The catalogue keeps one string
 * (`... em {settings}, na conta certa.`) and the screen supplies what `settings` renders.
 */
export function Trans({ text, values }: { text: string; values: Record<string, ReactNode> }) {
  const parts = text.split(/(\{\w+\})/g).filter((part) => part !== "");

  return (
    <>
      {parts.map((part, index) => {
        const match = /^\{(\w+)\}$/.exec(part);
        if (!match) return <Fragment key={index}>{part}</Fragment>;
        return <Fragment key={index}>{values[match[1] ?? ""]}</Fragment>;
      })}
    </>
  );
}
