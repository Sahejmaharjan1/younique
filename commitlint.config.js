module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "scope-enum": [
      2,
      "always",
      [
        "web",
        "backend",
        "connectors",
        "agents",
        "infra",
        "docs",
        "authz",
        "api-client",
        "ci",
        "crypto",
        "deps",
      ],
    ],
  },
};
