# zolotoy-dev-infra

Cross-service integration and deployment infrastructure for the `zolotoy.dev` backend portfolio.

This repository is intentionally **documentation-first at bootstrap time**. The Go service repositories
and production Selectel backend environment do not exist yet, so this initial commit does not pretend
that a runnable production Compose stack or deployment workflow has already been validated.

## Ownership

This repository will own:

- production/integration Docker Compose that consumes published service images;
- edge TLS and reverse-proxy configuration;
- cross-service Docker networks;
- shared Kafka and shared observability topology;
- environment inventory and public host mapping;
- production deployment/rollback procedures;
- cross-service backup/restore procedures;
- infrastructure-level smoke checks.

Individual service repositories continue to own their own `Dockerfile`, migrations, service-local
`compose.yaml`, health endpoint implementation and application configuration schema.

## Current state

As of 2026-09-06:

- `zolotoy-dev-frontend` is implemented and deployed through Cloudflare in the current project cycle;
- backend repositories are not yet created;
- no active `zolotoy.dev` Selectel backend deployment is claimed;
- this repo contains the accepted deployment direction and runbook scaffolding only.

The first active Compose/Caddy/deployment files should be added when there is at least one published,
smoke-testable backend service image.

## Planned edge topology

The frontend already defines separate service base URLs, so the initial backend deployment preserves
those public boundaries:

```text
order-api.zolotoy.dev         -> order-service
 auth-api.zolotoy.dev         -> auth-service
notification-api.zolotoy.dev  -> notification-service
shortener-api.zolotoy.dev     -> url-shortener management API
s.zolotoy.dev                 -> url-shortener public redirect path
```

Caddy is the preferred first edge because the existing `saypix`/`maxzolotoy.com` VPS workflow already
uses it successfully, and Caddy provides automatic HTTPS and reverse proxying. This is a project
operational reuse decision, not a requirement imposed on the Go services.

Only Caddy should expose public `80/443` on the single-VPS baseline. PostgreSQL, Redis, Kafka,
Prometheus metrics endpoints and service container ports remain internal unless an explicit
operational requirement says otherwise.

## Deployment strategy

Target progression:

```text
service repository
  -> verify/test
  -> build immutable image
  -> push to container registry
  -> select/promote image tag in zolotoy-dev-infra
  -> production environment gate
  -> docker compose pull
  -> docker compose up -d
  -> readiness/smoke checks
  -> rollback by previous immutable image set if needed
```

For Selectel, its managed Container Registry (`cr.selcloud.ru/<registry>/...`) is the preferred
candidate when backend deployment starts. The final registry choice should be recorded before the
first production workflow is added.

## Documentation

- [Architecture](docs/architecture.md)
- [Environment model](docs/environments.md)
- [Deployment plan](docs/deployment-plan.md)
- [Security baseline](docs/security.md)
- [Observability](docs/observability.md)
- [Backup and restore plan](docs/backups.md)
- [Bootstrap Selectel runbook](docs/runbooks/bootstrap-selectel.md)
- [Deployment runbook](docs/runbooks/deploy.md)
- [Rollback runbook](docs/runbooks/rollback.md)
- [ADRs](docs/adr/README.md)
- [Research references](docs/references.md)
- [Service inventory](inventory/services.yaml)

## Verification

This bootstrap has no runtime dependencies. Check repository integrity with:

```bash
python scripts/check_docs.py
git diff --check
```

When active Compose/Caddy/Terraform files are introduced, extend verification in the same change
(e.g. `docker compose config`, `caddy validate`, `terraform validate`) and document the exact command.

## No secrets in Git

Never commit production `.env`, SSH private keys, JWT signing keys, database passwords, registry
tokens, backup credentials or TLS private keys. See [docs/security.md](docs/security.md).

## License

No license is included yet because reuse terms have not been chosen explicitly.
