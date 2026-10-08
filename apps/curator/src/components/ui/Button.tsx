import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-(--color-accent) text-white hover:brightness-110 disabled:brightness-90",
  secondary: "bg-white text-(--color-ink) ring-1 ring-(--color-line) hover:bg-black/[0.03]",
  ghost: "text-(--color-muted) hover:bg-black/5 hover:text-(--color-ink)",
  danger: "bg-(--color-danger)/10 text-(--color-danger) ring-1 ring-(--color-danger)/25 hover:bg-(--color-danger)/15",
};

const SIZES: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs",
  md: "h-9 px-3.5 text-sm",
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    />
  );
}
