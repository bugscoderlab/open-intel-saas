import boundaries from "eslint-plugin-boundaries";
import tseslint from "typescript-eslint";

/** @type {import("eslint").Linter.Config[]} */
export default [
  ...tseslint.configs.recommended,
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { boundaries },
    settings: {
      "boundaries/elements": [
        {
          type: "features",
          pattern: "src/features/*/**",
          capture: ["feature"],
        },
      ],
      "import/resolver": {
        node: { extensions: [".ts", ".tsx", ".js", ".jsx"] },
      },
    },
    rules: {
      // Plan §14.1: feature folders may not import each other's internals.
      // The shared base is `features/platform`; cross-feature imports must
      // go through a declared contract later, so they fail lint today.
      "boundaries/element-types": [
        "error",
        {
          default: "allow",
          rules: [
            {
              from: "features",
              disallow: ["features"],
              message:
                "Feature folders may not import each other's internals (plan §14.1).",
            },
          ],
        },
      ],
    },
  },
];
