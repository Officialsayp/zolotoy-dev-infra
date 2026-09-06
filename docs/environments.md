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
- only Caddy public by default;
- secrets outside Git;
- persistent volumes backed up before risky schema/deployment operations;
- readiness and external smoke checks after deploy;
- documented previous image/config set for rollback.

## Frontend

The frontend remains independently deployable. Its current Cloudflare hosting does not require moving
to the VPS when the first backend is deployed. Backend service DNS can be introduced incrementally while
the production frontend remains in mock mode.
