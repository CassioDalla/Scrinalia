import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "neutral" | "ok" | "warn" | "danger" | "accent";

const TONES: Record<Tone, string> = {
  neutral: "bg-black/5 text-(--color-muted) ring-black/10",
  ok: "bg-(--color-ok)/10 text-(--color-ok) ring-(--color-ok)/25",
  warn: "bg-(--color-warn)/10 text-(--color-warn) ring-(--color-warn)/30",
  danger: "bg-(--color-danger)/10 text-(--color-danger) ring-(--color-danger)/25",
  accent: "bg-(--color-accent)/10 text-(--color-accent) ring-(--color-accent)/25",
};

export function Badge({
  children,
  tone = "neutral",
  title,
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  title?: string;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
