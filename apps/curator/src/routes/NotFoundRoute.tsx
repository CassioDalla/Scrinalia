import { Link } from "@tanstack/react-router";

import { EmptyState } from "@/components/ui/Feedback";

export function NotFoundRoute() {
  return (
    <div className="px-6 py-10">
      <EmptyState
        title="Tela não encontrada"
        hint="O endereço não corresponde a nenhuma tela implementada."
        action={
          <Link to="/" className="text-sm text-(--color-accent) hover:underline">
            Voltar ao início
          </Link>
        }
      />
    </div>
  );
}
