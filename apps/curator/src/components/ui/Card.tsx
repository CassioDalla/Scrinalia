import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-lg bg-(--color-surface) ring-1 ring-(--color-line)", className)}>{children}</div>
  );
}

export function CardHeader({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("border-b border-(--color-line) px-4 py-3", className)}>{children}</div>;
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("px-4 py-3", className)}>{children}</div>;
}
