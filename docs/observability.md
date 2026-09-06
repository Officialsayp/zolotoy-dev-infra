# Observability plan

The backend specs consistently call for structured logs and Prometheus/OpenTelemetry-oriented
instrumentation. Keep the initial shared stack small.

## Service-owned

Each service owns:

- structured `slog` fields and redaction;
- `/health/live` and `/health/ready` semantics where specified;
- `/metrics` instrumentation;
- trace propagation/instrumentation when OpenTelemetry is introduced;
- service-specific dashboards/alerts definitions when they become stable.

## Infra-owned

This repository owns:

- Prometheus scrape topology;
- shared Grafana provisioning;
- optional OTel Collector routing after services emit telemetry;
- retention/resource configuration based on measured VPS capacity;
- access restrictions for observability UIs.

## Do not overbuild

Do not add ELK/Loki/Tempo/ClickHouse merely to increase stack size. Notification and Shortener specs
already provide enough operational depth. Add a telemetry backend only when there is a concrete query,
retention or debugging requirement.

Prometheus configuration should be validated before reload/deploy. A syntactically valid configuration
is not proof that targets are reachable; target health must be checked after deployment.
