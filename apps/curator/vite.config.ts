import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { reactClickToComponent } from "vite-plugin-react-click-to-component";

// The dev server proxies the API instead of the browser calling it cross-origin, which is what
// keeps CORS out of the project entirely: in development the proxy answers, and in production the
// built files are served by Litestar from the same origin as the API.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    /*
      Alt+right click on a screen opens the element under the cursor in the editor. It is the tool
      for a **copy** pass — "which file says this sentence?" — and it is dev-only by construction:
      every hook of the plugin returns early unless ``config.command === "serve"``, so the built
      bundle carries nothing of it (measured: 0 occurrences of ``click-to-component`` in
      ``dist/assets/*.js``).

      It is here and not a component gallery (Ladle, a ``/dev`` route) because the unit of this
      interface is the **screen with real data**, which is what the copy has to read well inside:
      a sentence that fits a gallery's 200px can wrap to three lines in a real header. The plugin
      also lands on the exact line of the clicked element, not on the component's definition, which
      is where the string actually is.

      **It only works against this dev server**, never against the built SPA the API serves at
      ``/``: the production transform emits no ``jsxDEV`` at all (measured: 0 ``fileName``, 0
      ``lineNumber`` in ``dist``). And it needs the patch below, because **React 19 dropped the
      ``source`` argument from ``jsxDEV``** — ``react-jsx-dev-runtime.development.js`` declares
      ``ReactElement(type, key, props, owner, debugStack, debugTask)`` and
      ``jsxDEV(type, config, maybeKey, isStaticChildren)``, with ``_debugInfo`` fixed at ``null``.
      The transform still passes ``{ fileName, lineNumber, columnNumber }`` (it is in the served
      module), React throws it away, and every tool that reads the source off the fiber — a browser
      extension included — therefore finds nothing. The plugin is the one that threads it back.
    */
    reactClickToComponent(),
  ],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      /*
        ``changeOrigin`` stays **false** on purpose: the API's ``origin_guard`` compares the
        ``Origin`` a mutating request carries with the ``Host`` it was addressed to, and rewriting
        Host to ``localhost:8000`` would make every dev mutation look cross-origin and answer 403.
        Preserving the host keeps development same-origin, which is what production already is.
      */
      "/api": { target: "http://localhost:8000" },
      "/schema": { target: "http://localhost:8000" },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
