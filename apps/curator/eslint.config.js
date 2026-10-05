import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/api/schema.d.ts"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // The rule that keeps the contract real. Every request must go through the generated client,
      // because a hand-written ``fetch`` is invisible to the OpenAPI check and drifts silently —
      // the risk the ADR names explicitly.
      "no-restricted-globals": [
        "error",
        { name: "fetch", message: "Use o client gerado em src/api/client.ts (openapi-fetch)." },
      ],
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.name='fetch']",
          message: "Use o client gerado em src/api/client.ts (openapi-fetch).",
        },
      ],
    },
  },
);
