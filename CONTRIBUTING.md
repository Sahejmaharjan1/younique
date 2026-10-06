# Contributing

## Setup

```bash
make setup
make dev
```

Commits use Conventional Commits and must include a `Signed-off-by` line (DCO). There is no CLA.

## Where to put a change

| I want to... | Put it in |
| --- | --- |
| Add an integration | `connectors/{key}/` |
| Add a model | `packages/model-registry/models.yaml` |
| Add an endpoint | `backend/src/younique/api/` and call `authorize()` |
| Add business logic | `backend/src/younique/services/` |
| Change permissions | `backend/src/younique/authz/policy.py` and `backend/tests/authz/expectations.yaml` |
| Change infrastructure | `infra/terraform/modules/` then each environment |

## Before a pull request

- Tests cover the behaviour you changed.
- An endpoint change regenerates `openapi.json`.
- A permission change updates the expectation fixture.
- A connector tool sets its risk class and `produces_untrusted_content`.
- Migrations are expand-and-contract and do not touch the `langgraph` schema.

See [AGENTS.md](AGENTS.md) for the rules that apply to every change.
