# Rules File Drafts

These are drafts of the rules files that AI coding assistants and human contributors read
before touching code. Each one is copied to its final location during Phase 0:

| Draft | Final location |
| --- | --- |
| [root-AGENTS.md](root-AGENTS.md) | `/AGENTS.md`, with `/CLAUDE.md` as a symlink |
| [web-AGENTS.md](web-AGENTS.md) | `/apps/web/AGENTS.md` |
| [backend-AGENTS.md](backend-AGENTS.md) | `/backend/AGENTS.md` |
| [agents-AGENTS.md](agents-AGENTS.md) | `/backend/src/younique/agents/AGENTS.md` |
| [connectors-AGENTS.md](connectors-AGENTS.md) | `/connectors/AGENTS.md` |
| [infra-AGENTS.md](infra-AGENTS.md) | `/infra/AGENTS.md` |
| [tests-AGENTS.md](tests-AGENTS.md) | `/backend/tests/AGENTS.md` and `/apps/web/e2e/AGENTS.md` |
| [recipes.md](recipes.md) | `/docs/site/contributing/recipes.md`, and linked from each area file |

## Why nested rules files

An assistant editing `connectors/notion/tools/create_page.py` should not have to read the
frontend conventions to know what to do, and it should not be able to *miss* the connector
conventions. Nested files put the right constraints in scope automatically.

## Style rules for these files

1. **Imperative and specific.** "Never import `httpx` directly in a connector; use `ctx.http`"
   beats "be careful with HTTP clients".
2. **State the reason for anything non-obvious**, in one clause. A rule without a reason gets
   worked around the first time it is inconvenient.
3. **Point to the design doc rather than restating it.** These files go stale when they
   duplicate content.
4. **Lead with the things that are irreversible or dangerous.** An assistant reads the top.
5. **Keep them short.** Under 200 lines each. A 1000-line rules file is skimmed.
