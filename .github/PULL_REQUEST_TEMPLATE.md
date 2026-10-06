## Summary

-

## Checklist

- [ ] `Signed-off-by` present (DCO)
- [ ] Tests for the behaviour I changed
- [ ] Touched an endpoint? `authorize()` dependency present, `openapi.json` regenerated
- [ ] Touched permissions? `tests/authz/expectations.yaml` updated
- [ ] Added a connector tool? Risk class set, `summarize_for_approval` written if high risk, `produces_untrusted_content` set correctly
- [ ] Migration? Expand-and-contract, reviewed the generated SQL, `CONCURRENTLY` for indexes on existing tables
- [ ] No secrets, no `print`, no `float` for money
