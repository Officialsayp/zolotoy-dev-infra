# Runbook — deploy backend stack

Status: process skeleton until active Compose/workflows exist.

## Before deployment

- confirm explicit deployment authorization;
- identify desired immutable image tags/digests;
- capture current deployed image/config set;
- verify repository/config checks;
- assess database migration compatibility and backup requirement;
- confirm production environment secrets are available without printing them.

## Deployment

The expected single-host pattern is eventually:

```bash
docker compose -f compose.yaml -f compose.production.yaml pull
docker compose -f compose.yaml -f compose.production.yaml up -d
```

Exact filenames/services must match the real committed configuration before this command becomes
operational guidance.

## Verification

Do not stop at container state. Verify:

- Compose container health;
- each deployed service readiness endpoint;
- the verified active HTTP(S) edge and TLS for the public hostname;
- representative API request;
- Kafka/DB/Redis dependency health where relevant;
- Prometheus target health after observability exists.

Record any partial failure and use the rollback runbook rather than stacking unreviewed changes.
