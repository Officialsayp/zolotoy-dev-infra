## Change type

- [ ] Documentation / ADR
- [ ] Integration configuration
- [ ] Production configuration
- [ ] Deployment / rollback automation
- [ ] Observability / backup

## Safety

- [ ] No secrets or private keys are committed.
- [ ] Public port exposure is intentional and documented.
- [ ] Proposed state is not described as already deployed.
- [ ] Rollback/data-migration implications are documented when relevant.
- [ ] Service contracts/ports/health paths came from the owning service, not guesswork.

## Verification

- [ ] `python scripts/check_docs.py`
- [ ] `git diff --check`
- [ ] Relevant Compose/Caddy/Terraform validation (only if those files exist/change)
- [ ] Live smoke/restore checks reported separately when an actual environment changed
