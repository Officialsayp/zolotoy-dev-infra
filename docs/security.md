# Infrastructure security baseline

## Secrets

Never commit:

- production `.env` files;
- database/Redis passwords;
- JWT signing private keys;
- SSH private keys;
- Selectel registry tokens;
- S3/restic credentials;
- TLS private keys;
- provider/API tokens.

Docker Compose supports service-scoped secrets. When the Go service configuration supports file-based
secret loading, prefer mounted secret files over broad environment-variable exposure. Host-side secret
files remain sensitive and should be stored outside the repository with restrictive permissions.

## Network exposure

Default-deny by design:

- public: Caddy 80/443;
- private/internal: Go service ports, PostgreSQL, Redis, Kafka, Prometheus scrape endpoints;
- local/admin only: Grafana unless authenticated/restricted, Kafka UI, Mailpit, Portainer if ever used.

Do not use `0.0.0.0` host publishing for a data/admin service by convenience.

## TLS

Caddy automatic HTTPS is the initial edge plan. Do not disable upstream TLS verification when proxying
to an HTTPS upstream. Inside one controlled Docker network, plaintext HTTP from Caddy to the service can
be preferable to fake HTTPS with verification disabled.

## CI/CD

GitHub recommends least-privilege workflow permissions and immutable full commit SHAs for actions.
Production secrets belong to a protected GitHub Environment, not the repository or workflow file.

## Application security boundary

Infrastructure does not replace application controls:

- Auth owns cookie/JWT/CSRF/session security;
- services own authorization and input validation;
- Caddy is not the authority for business RBAC;
- frontend route guards are not backend authorization.
