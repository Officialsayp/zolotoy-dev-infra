# ADR 0002 — Single-VPS Docker Compose first

- Status: Accepted
- Date: 2026-09-06

## Context

The goal is an interview-ready portfolio, not a production marketplace requiring a cluster. The stack
will include multiple Go services plus PostgreSQL/Redis/Kafka and observability.

## Decision

Start the production-like deployment on one Selectel VPS using Docker Compose. Size the VPS only after
real service measurements exist. Kubernetes/Helm remains a stretch goal.

## Consequences

- deployment/recovery stays explainable;
- resource contention is visible and measurable;
- host failure is a single point of failure, acceptable for the portfolio baseline;
- scaling/high availability are architectural discussion topics rather than fake complexity;
- service boundaries still remain logical even on one machine.
