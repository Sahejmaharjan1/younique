# Younique

Younique is an open-source AI workspace. You connect services you already use, bring your own model keys, and approve anything the agent does that is hard to undo.

## Quickstart

```bash
git clone https://github.com/younique/younique && cd younique
make setup
make dev
```

`make dev` starts Postgres, the Firebase Auth emulator, fake GCS, a Cloud Tasks shim, ClamAV, and Langfuse. No GCP account is required. The API health check is `http://127.0.0.1:8000/healthz` and the web app is `http://127.0.0.1:3000`.

## What the MVP does

Sign in, accept versioned terms, save a provider key, and stream a chat. Send mail through SMTP (or Gmail with your own OAuth client) only after you approve it. Uploaded files are scanned before download. A share link can read one chat and nothing else.

## Docs

Start at [docs/README.md](docs/README.md). Architecture decisions are in [docs/adr](docs/adr). Contributor rules are in [AGENTS.md](AGENTS.md).

## License

The application is AGPL-3.0-only. `packages/api-client`, `packages/sdk`, and `connectors/_sdk` are Apache-2.0. Documentation is CC-BY-4.0.
