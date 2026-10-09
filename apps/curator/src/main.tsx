import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { PRODUCT } from "@/lib/copy";
import { router } from "@/router";
import "@/styles.css";

// The tab's title, from the one definition of the product's name. `index.html` boots neutral on
// purpose, so a rename is still a change to `lib/attribution.ts` and nothing else.
document.title = PRODUCT.documentTitle;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The archivist's browser is on the same network as the API, so a failure is usually a real
      // failure rather than a flaky connection. Retrying twice is enough to absorb a restart.
      retry: 2,
      refetchOnWindowFocus: true,
    },
  },
});

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("#root não encontrado no index.html");

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
