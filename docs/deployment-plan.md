# Deployment plan

## Why no deploy workflow is committed yet

The backend repository now exists (`Officialsayp/zolotoy-dev-backend`) with a developing Order service,
but no validated production backend image or ready-to-deploy Compose contract is recorded here. A live
workflow today would require inventing image digests, readiness behavior or infrastructure credentials.
Keep deployment documentation and review gates until the first real service image and contract are verified.

## Image lifecycle

Recommended model when service CI exists:

1. service CI runs formatting/lint/tests/build/security checks appropriate to that service;
2. build a container image from the service repository;
3. push it to the selected registry with an immutable Git-SHA-derived tag;
4. optionally add a human-readable release tag, but do not deploy by mutable `latest`;
5. record/promote the desired immutable image set in this repository;
6. deploy through a GitHub `production` Environment or an explicitly authorized manual run;
7. execute readiness and external smoke checks;
8. retain the previous immutable image set for rollback.

Selectel Container Registry is a natural candidate because it supports Docker CLI login/push/pull at
`cr.selcloud.ru/<registry>/...`. Record the final registry decision before writing production workflow
secrets/variables.

## Compose model

Docker recommends environment-specific Compose overrides for production. The eventual structure should
prefer a base integration definition plus a production override rather than host bind-mounting source
code into production containers.

Expected active files **later**, not placeholders now (use Nginx instead of Caddy if the live edge audit establishes that choice):

```text
compose.yaml
compose.production.yaml
deploy/caddy/Caddyfile
observability/prometheus/prometheus.yml
observability/grafana/provisioning/...
```

Add only the files that can be validated against real images/config.

## GitHub Actions baseline

When deployment automation is introduced:

- `permissions: contents: read` unless more is genuinely needed;
- use a GitHub Environment named `production` for production secrets/gates;
- use `concurrency` so only one production deploy runs at a time;
- pin third-party actions to verified full-length commit SHAs;
- do not echo credentials;
- prefer short-lived/scoped registry credentials when supported;
- separate verify/build from deploy;
- make `push to main` deployment behavior explicit in README/AGENTS before enabling it.
