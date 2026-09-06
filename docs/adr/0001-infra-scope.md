# ADR 0001 — Infrastructure repository scope

- Status: Accepted
- Date: 2026-09-06

## Context

Each backend specification already requires its own Dockerfile, local Compose, migrations and health
checks. A separate infra repository is still useful for cross-service production/integration concerns.

## Decision

`zolotoy-dev-infra` owns cross-service deployment topology, edge routing, shared Kafka/observability,
backups and operational runbooks. Service-local development infrastructure remains in service repos.

## Consequences

- one service remains independently runnable;
- production Compose consumes published images instead of sibling source trees;
- migrations stay next to service code;
- cross-service operational changes have one review surface;
- some configuration concepts intentionally exist at both service-local and production levels, but
  canonical ownership remains explicit.
