import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { LocaleProvider } from "@/i18n/context";
import { activeMessages } from "@/i18n/locale";
import { router } from "@/router";
import "@/styles.css";

// The tab's title, from the catalogue. `index.html` boots neutral on purpose, so a rename is still a
// change to `lib/attribution.ts` and nothing else.
document.title = activeMessages().product.documentTitle;

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
if (!rootElement) throw new Error("#root not found in index.html");

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <LocaleProvider>
        <RouterProvider router={router} />
      </LocaleProvider>
    </QueryClientProvider>
  </StrictMode>,
);
