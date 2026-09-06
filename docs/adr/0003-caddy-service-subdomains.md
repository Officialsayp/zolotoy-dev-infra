# ADR 0003 — Caddy edge with service subdomains

- Status: Accepted for the first backend deployment
- Date: 2026-09-06

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
