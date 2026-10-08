import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-(--color-line) bg-(--color-surface) px-6 py-4">
      <div className="min-w-0">
        <h1 className="truncate text-lg font-semibold">{title}</h1>
        {subtitle ? <div className="mt-0.5 text-sm text-(--color-muted)">{subtitle}</div> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}
