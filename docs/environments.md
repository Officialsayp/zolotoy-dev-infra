# Environments

## Local service development

Owned by each service repository. The service's own Compose should be enough to run its immediate
PostgreSQL/Redis/Kafka dependencies for focused development.

## Cross-service integration

Owned here once two or more real service images/contracts need to be exercised together. It may add
Kafka, shared observability and routing, but it should consume service images instead of rebuilding
source from sibling paths.

## Production-like Selectel

Planned, not active at bootstrap time.

Principles:

- immutable image versions;
- one controlled deployment at a time;
- only the verified active HTTP(S) edge (Caddy or Nginx) public by default;
- secrets outside Git;
- persistent volumes backed up before risky schema/deployment operations;
- readiness and external smoke checks after deploy;
- documented previous image/config set for rollback.

## Frontend

The frontend remains independently deployable, with Cloudflare and Selectel deployment tooling present in
its repository. Verify live DNS, active host and certificate management before assuming where production
currently runs. Backend service DNS can be introduced incrementally while the frontend uses mock mode.
