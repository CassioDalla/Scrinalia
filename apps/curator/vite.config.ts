import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies the API instead of the browser calling it cross-origin, which is what
// keeps CORS out of the project entirely: in development the proxy answers, and in production the
// built files are served by Litestar from the same origin as the API.
export default defineConfig({
  plugins: [react(), tailwindcss()],
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
