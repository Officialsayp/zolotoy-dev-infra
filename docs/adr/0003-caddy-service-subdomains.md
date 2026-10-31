# ADR 0003 — Caddy edge with service subdomains

- Status: Accepted for the first backend deployment
- Date: 2026-09-06

> **Revalidation note (2026-10-31):** This records the original preferred first backend edge, not a
> verified description of today's VPS. Both Caddy and Nginx profiles now exist in site repositories.
> Preserve the accepted historical decision; selecting a different active backend edge requires a
> live-state audit and a new superseding ADR, not an implicit rewrite of this record.

## Context

The frontend environment template already declares separate public base URLs for Order, Auth,
Notification and Shortener plus `s.zolotoy.dev`. The existing `saypix` VPS workflow has proven Caddy as
an operationally familiar HTTPS edge for this project owner.

## Decision

Use Caddy as the first Selectel edge and preserve service-specific public hostnames. Do not introduce a
new `api.zolotoy.dev` gateway layer before a concrete requirement exists.

## Consequences

- frontend configuration can align with its existing service registry;
- TLS/routing failures are isolated by service hostname;
- browser CORS/credentials policy must be configured correctly for cross-origin API calls;
- Caddy becomes infrastructure, not business authorization;
- a future same-origin/API-gateway design requires a new ADR and frontend configuration update.
