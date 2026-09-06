# AGENTS.md — zolotoy-dev-infra

Repository instructions for cross-service infrastructure of `zolotoy.dev`.

## Instruction scope and precedence

- Follow system/developer/tool instructions, then explicit user instructions.
- This file applies repository-wide; read narrower `AGENTS.md` / `AGENTS.override.md` if added later.
- Start with `git status --short`, relevant diffs and the runbook/ADR for the affected environment.
- Preserve user work and make the smallest cohesive operational change.
- Infrastructure plans are not proof of production state. Verify live state before operational work.

## Source ownership

| Concern | Owner/source |
| --- | --- |
| Business/API behavior | Service repository / canonical OpenAPI |
| Service Dockerfile, migrations, local Compose | Service repository |
| Frontend runtime/base URL behavior | `Officialsayp/zolotoy-dev-frontend` |
| System-level repo boundaries | `Officialsayp/zolotoy-dev` |
| Production/integration topology, edge, shared ops | This repository |
| Actual deployed state | Active config + runbook + live verification |

Do not reimplement service business logic here or make infrastructure config a hidden API contract.

## Bootstrap rule

Until a backend image exists, keep this repository documentation-first. Do not add a fake production
Compose file full of non-existent images/ports merely to make the tree look complete. Add runnable
artifacts when they can be validated against real service contracts and health endpoints.

## Target principles

- Single Selectel VPS + Docker Compose is the first production-like target; Kubernetes/Helm is a
  stretch goal, not a prerequisite.
- Prefer Caddy for the initial TLS/reverse-proxy edge to reuse the operational model already proven in
  `Officialsayp/saypix`; do not copy unrelated IPs/domains/secrets from that project.
- Keep only edge ports public. Databases, Redis, Kafka, internal metrics and admin tooling stay on
  private/internal networks unless explicitly justified.
- Service repositories remain independently runnable. This repo consumes built images; it does not
  become the only development environment.
- Preserve service data ownership. Physical consolidation for a small VPS must not permit cross-service
  tables, migrations or direct SQL dependencies.
- Kafka is shared integration infrastructure; consumer semantics and event handling remain service code.
- Shared observability may include Prometheus/Grafana and, when instrumented, an OTel Collector. Do not
  add ELK/Loki/Tempo/ClickHouse just for architecture decoration.

## Secrets and security

- Never commit secrets. Real `.env`, SSH keys, JWT signing keys, DB passwords, registry credentials,
  S3/restic credentials and TLS private keys stay outside Git.
- Prefer Docker Compose secrets/file mounts for sensitive runtime values instead of broad environment
  variables where service configuration supports it. Host secret files must be permission-restricted.
- In GitHub Actions, use minimal `permissions`, GitHub Environments for production gates/secrets and
  immutable full commit SHAs for third-party actions when workflows are added.
- Do not expose Portainer, Kafka UI, Prometheus, Grafana or database ports publicly by default.
- Avoid `tls_insecure_skip_verify`, wildcard firewall openings and privileged containers without an
  explicit threat/operational justification.

## Deployment safety

Operational writes require explicit authorization. Before a production change:

1. identify affected services/data;
2. capture the current deployed image/config set;
3. validate configuration locally/CI;
4. confirm backup/restore implications for schema changes;
5. deploy with one production concurrency lane;
6. verify readiness and external smoke checks;
7. keep an executable rollback path.

Do not treat `docker compose up -d` success as application readiness. Use service readiness endpoints
and user-visible/API smoke checks.

Never force-push, delete production resources, prune volumes, reset databases, rotate keys or modify DNS
without explicit authorization for that destructive/external action.

## Change discipline

- Update an ADR when changing a durable architecture choice (edge, registry, deployment model, data
  topology), not for routine version bumps.
- Update the runbook whenever the actual deployment or recovery procedure changes.
- Pin production images to immutable digests or Git-SHA-derived tags; avoid relying on `latest` for
  rollback-critical deployment.
- Prefer production override/compose files to source-code bind mounts. Keep application code inside
  built images.
- Add resource limits/healthchecks/restart behavior based on measured service needs, not invented values.

## Verification

Bootstrap/docs changes:

```bash
python scripts/check_docs.py
git diff --check
```

Once corresponding files exist, expected checks include:

```bash
docker compose config
caddy validate --config <Caddyfile> --adapter caddyfile
```

Add Terraform validation only if Terraform is actually introduced. Report unavailable checks honestly;
do not claim a deploy or restore test from static validation.

## Maintaining these instructions

This file takes its workflow/safety foundation from `Officialsayp/saypix/AGENTS.md` (runbooks,
rollback, no secret leakage, live-state verification) and `Officialsayp/zolotoy-dev-frontend/AGENTS.md`
(source hierarchy, bounded context reading, explicit TBD contracts, focused verification). Keep durable
rules here and detailed procedures under `docs/`.
