const tsParser = require("@typescript-eslint/parser");

module.exports = [
  { ignores: [".next/**", "node_modules/**"] },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { parser: tsParser, ecmaVersion: "latest", sourceType: "module" },
  },
];
