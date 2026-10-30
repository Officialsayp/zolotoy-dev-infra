# Portable VPS migration and disaster recovery

Status: **repository-based procedure, not a live-host audit or a tested bare-metal recovery**. Updated: 2026-10-31.

Related source-of-truth documents:
- [saypix recovery runbook](https://github.com/Officialsayp/saypix/blob/main/docs/recovery-runbook.md)
- [zolotoy.dev Selectel production](https://github.com/Officialsayp/zolotoy-dev-frontend/blob/main/docs/deployment/SELECTEL_PRODUCTION.md)
- [zolotoy.dev Nginx](https://github.com/Officialsayp/zolotoy-dev-frontend/blob/main/docs/deployment/NGINX.md)
- [zolotoy.dev TLS recovery](https://github.com/Officialsayp/zolotoy-dev-frontend/blob/main/docs/deployment/SELECTEL_TLS_RECOVERY.md)
- [backend deployment plan](../deployment-plan.md)

These documents include historical Caddy instructions and later Nginx profiles. **Which web server and certificate renewal mechanism are actually active must be read from the existing VPS**; repository files alone do not prove installed state.

## Scope and recovery boundaries

- maxzolotoy.com: Officialsayp/saypix, static releases under /var/www/maxzolotoy/releases and atomic /var/www/maxzolotoy/current. Both Caddy and Nginx source profiles exist.
- zolotoy.dev: Officialsayp/zolotoy-dev-frontend, production /var/www/zolotoy-dev-production/current and separate staging /var/www/zolotoy-dev/releases/current. GitHub contains Selectel production/staging deployment workflows and Cloudflare tooling; verify active public DNS and listener before migration.
- Backend: Officialsayp/zolotoy-dev-backend contains a developing Go Order service. Auth, Notification, Shortener and PostgreSQL/Redis/Kafka deployment are planned; no verified backend production Compose/image set currently exists.
- This repository owns cross-service desired configuration and procedures; actual deployed state must be recorded from the host. Never infer production from an outdated README.

## 1. Gather evidence before making changes (read-only)

On the original VPS, with an authorized account, collect:
- OS and architecture: cat /etc/os-release; uname -m
- Capacity: free -h; df -hT; lsblk -f
- Current services/timers: systemctl --no-pager --type=service --state=running; systemctl list-timers --all --no-pager
- Listener ownership: sudo ss -lntup
- Edge config: sudo systemctl status caddy nginx --no-pager; sudo nginx -t where installed; Caddy validate where installed
- Active releases: readlink -f /var/www/maxzolotoy/current; readlink -f /var/www/zolotoy-dev-production/current; readlink -f /var/www/zolotoy-dev/releases/current
- Docker: docker ps and docker volume ls, only if Docker is installed
- TLS: identify issuer, active certificate paths, expiration and systemd/ACME renewal units; never print private keys
- Backup: inventory schedules, most recent successful off-host snapshots, restore credentials and retention without revealing secrets
- Accounts: authorized deploy users, filesystem access, SSH host fingerprints, UFW/provider firewall and permissions
- GitHub: environment names, deployment gating variables, expected secret **names**, current deployed SHAs and last workflow results
- DNS: actual A/AAAA/CNAME records, Cloudflare proxy mode, TTL, origin hosts, mail/verification records

Redact secrets and private operator data before sharing diagnostics. Preserve verified copies of config, systemd units, firewall policy and certificate-renewal scripts **outside the old VPS**. Do not copy root-owned production TLS private keys into repositories.

## 2. Backup and restore prerequisites

1. Record exact known-good commits, immutable site release IDs and existing symlink targets; keep old releases during migration.
2. Check an isolated restore of the saypix restic backup from Selectel S3. The saypix backup in region ru-1 must **not** be assumed to include zolotoy.dev, PostgreSQL or Kafka.
3. Verify that frontend production configuration and non-reconstructible runtime files are saved separately; test their restore to a temporary directory.
4. When databases exist, make database-aware PostgreSQL backups, include migration/version metadata and test restore. Define Redis persistence per use case. A single Kafka KRaft broker is not highly available and retention is not a backup.
5. Store access to GitHub, DNS, registries, Selectel/S3 and encryption credentials in an independent secret store. Never place plaintext secret values in Git or chat.
6. Explicitly agree recovery-point objective (RPO), recovery-time objective (RTO), maintenance window and stateful write-freeze/replication strategy. **None is proven by this document.**

## 3. Provision replacement VPS (requires approval)

- Choose a provider/region supported by the intended users and service integrations. Match architecture and sufficient CPU, RAM and disk for *actual* services, plus Kafka/Prometheus log growth and backups.
- Provision a supported Linux release. Set up non-root SSH users, authenticated host keys, key-only access, restrictive filesystem permissions, security updates and firewall. Limit external access to HTTP/HTTPS and approved SSH sources. Never expose PostgreSQL, Redis, Kafka, metrics or admin tooling publicly.
- Install exact required packages based on inspected live state (Nginx + njs/headers-more modules, or Caddy; Docker/Compose only if actually used). Package names and versions must be checked for the new OS.
- Re-create release directories and least-privilege ownership so the HTTP server can read active releases while deploy accounts cannot access TLS keys or unrelated apps.
- Restore **reviewed** configs, timers, alerts and renewal scripts from backups/source. Stage restored files to a temporary path and inspect their permissions and contents before controlled installation; never blindly extract backup archives over /.

## 4. TLS, CI/CD and website recovery

- Verify the actual certificate issuance and renewal mechanism for each hostname. zolotoy.dev uses a .dev domain with HSTS preload: valid HTTPS must work before public cutover. **HTTP-01 alone usually cannot issue a certificate for the new host while public DNS still points to the old host.** Prefer a verified DNS-01 procedure where supported, or securely reuse an existing valid certificate/key under strict permissions and explicitly set up renewal on the replacement host. Check SAN/hostname coverage and avoid simultaneously competing ACME renewals. Certificate keys must be replaced if compromise is suspected.
- Reconfigure GitHub Environment deploy host, user, verified SSH host key and private key **out of band**. Retain current concurrency locks, protected branches and environment approvals. Freeze simultaneous old/new deploys during cutover.
- Deploy saypix through its tested atomic-release workflow. Preserve its language routing, apex/www redirects, cache/security headers, health endpoints, and site-specific backup/rotation timers.
- Deploy frontend through the already tested exact-artifact Selectel workflow, keeping production and staging separate. Check canonical pages, RU/EN, /demo/ nested routes, MSW assets, sitemap/robots and release/health endpoints.
- Test a hostname against the new IP **before DNS changes**, using a valid new-host TLS configuration. Example:
  curl --resolve maxzolotoy.com:443:NEW_IP -I https://maxzolotoy.com/ru/
  curl --resolve zolotoy.dev:443:NEW_IP -I https://zolotoy.dev/
- Repeat real browser and HTTP tests from relevant Russian and foreign networks; confirm downloaded asset sizes and protocol behavior.

## 5. Future backend recovery, only when deployed

- Use the *real* reviewed, pinned Docker Compose definitions and immutable image digests from this repository and service repos. No fabricated images/ports.
- Restore PostgreSQL roles/databases and compatible schema before releasing application writers; never blindly roll back an incompatible migration. Recover only required persistent Redis data.
- Restore broker configuration and assess Kafka event/replay consistency against database outbox and consumer contracts before resuming event publication.
- Start private dependencies and readiness-verified service images; activate only approved public API hostnames after end-to-end smoke tests. Keep sensitive resources internal.
- Do not use docker compose down -v or unrestricted volume/image pruning during recovery.

## 6. DNS cutover and rollback

1. Record/export existing DNS zone and Cloudflare records. Preserve MX, SPF, DKIM, DMARC, Proton and verification records when changing web routing.
2. Only after successful independent new-host testing, authorize updates to web A/AAAA/CNAME and intended proxy modes. DNS propagation and existing connections mean zero downtime cannot be promised.
3. Verify certificates, static sites, APIs (when present), health/smoke checks, renewal jobs and alerts from multiple networks.
4. Retain the old VPS, old deployment records and backups during a documented rollback window. For stateless failure, redirect DNS to the known-good origin and/or revert release symlinks.
5. **Do not route stateful writes back to stale data**. A database rollback requires a consistency plan, writer isolation and data migration/replication assessment.
6. Update operational inventory with actual provider, IP/hostnames (not secrets), active Nginx/Caddy configs, deployed SHAs, RPO/RTO and tested restore evidence.

## 7. Remaining automation work (do not claim it exists)

Repository CI/CD for both sites is extensive, but a reproducible whole-VPS IaC bootstrap and a tested backend GitOps deploy are **not yet demonstrated**. First backend deployment requires a real Dockerfile/image, readiness endpoint, persistent data contract, and registry choice. Add tested Compose, edge route generation, staged deploy gates, smoke tests and rollback only when a service meets those prerequisites. Do not convert documentation-only services into fictitious running containers.

**Acceptance criterion for a truly portable move:** a rehearsed restore of both sites and all existing state from Git + independent backups, proven TLS renewal, CI/CD to the new host, live DNS cutover and a successfully tested rollback. Until then this is a documented recovery plan, not a promise of seamless migration.
