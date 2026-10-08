import type { InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-md bg-white px-3 text-sm ring-1 ring-(--color-line) placeholder:text-(--color-muted)/70",
        "focus:ring-2 focus:ring-(--color-accent) focus:outline-none disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}

export function Select({
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 w-full rounded-md bg-white px-2 text-sm ring-1 ring-(--color-line) focus:ring-2 focus:ring-(--color-accent) focus:outline-none",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full rounded-md bg-white px-3 py-2 text-sm ring-1 ring-(--color-line) focus:ring-2 focus:ring-(--color-accent) focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}
