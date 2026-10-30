# Portable VPS migration and disaster recovery

Status: **repository-based procedure, not a live-host audit or a tested bare-metal recovery**. Updated: 2026-10-31.

Related source-of-truth documents:
- [saypix recovery runbook](https://github.com/Officialsayp/saypix/blob/main/docs/recovery-runbook.md)
- [zolotoy.dev Selectel production](https://github.com/Officialsayp/zolotoy-dev-frontend/blob/main/docs/deployment/SELECTEL_PRODUCTION.md)
- [zolotoy.dev Nginx](https://github.com/Officialsayp/zolotoy-dev-frontend/blob/main/docs/deployment/NGINX.md)
- [zolotoy.dev TLS recovery](https://github.com/Officialsayp/zolotoy-dev-frontend/blob/main/docs/deployment/SELECTEL_TLS_RECOVERY.md)
- [backend deployment plan](../deployment-plan.md)

These documents include historical Caddy instructions and later Nginx profiles. **Which web server and certificate renewal mechanism are actually active must be read from the existing VPS**; repository files alone do not prove installed state.

## Operator-observed VPS baseline (2026-10-31)

The owner supplied read-only terminal output from the current Selectel VPS on 2026-10-31. This is
**observational evidence for that host only**, not an independent agent SSH audit or public DNS check:

- Ubuntu 26.04.1 LTS, x86_64; 956 MiB RAM, no swap; 9.8 GiB root filesystem with 5.7 GiB available.
- Nginx **active/enabled**, listening on TCP 80/443 on IPv4/IPv6; Caddy **inactive/disabled**.
- `nginx -t` passed; `caddy validate` also passed but **does not mean Caddy is serving traffic**.
- Active symlinks exist for `/var/www/maxzolotoy/current`,
  `/var/www/zolotoy-dev-production/current`, and `/var/www/zolotoy-dev/releases/current`.
- Docker is **not installed**; no Docker Compose or backend container deployment can currently run there.
- Timers listed: `certbot.timer`, `maxzolotoy-offsite-backup.timer`,
  `maxzolotoy-restic-check.timer`. Their presence **does not prove renewal or backup success**.
- A later systemd inventory identified `zolotoy-dev-certificate.timer` as **installed but disabled**. It was absent from the filtered *active timer schedule*, not absent from the host. All five Certbot renewal configurations exist; the installed legacy timer must remain disabled pending live renewal verification.

### TLS and backup evidence from owner-supplied VPS output (2026-10-31)

This is another **operator-provided read-only observation**, not a renewal simulation, a public-network verification or a restore drill:

- `sudo certbot certificates` lists five valid separate ECDSA Let's Encrypt certificates: `maxzolotoy.com`, `www.maxzolotoy.com`, `origin.maxzolotoy.com`, `zolotoy.dev`, `origin.zolotoy.dev`, each expiring 2027-01-28 at approximately 19:29–19:30 UTC.
- Local loopback HTTPS SNI checks on Nginx port 443 showed matching certificate subjects/SANs and expiry dates for all five hostnames. This does **not** establish that external DNS or remote network access works.
- `certbot.timer` is enabled. `certbot.service` reported Result=success and exit code 0, but no execution timestamp in the supplied output. An automated renewal and certificate installation into Nginx have **not** yet been proven by the timer.
- Legacy `zolotoy-dev-certificate.timer` is disabled; this is consistent with an intended migration away from its previous lego-based renewal, but verify Certbot covers the corresponding domain before treating it as decommissioned.
- `maxzolotoy-offsite-backup.service` and `maxzolotoy-restic-check.service` reported Result=success on 2026-10-30 at ~21:19 UTC. This proves successful service exits, **not** existence/contents of an up-to-date off-site snapshot or a successful restore.
- `maxzolotoy-config-backup.timer` is disabled. The newest listed local `/var/backups/maxzolotoy/config-*.tar.gz` archive was written **2026-10-30 00:02** UTC, before the five current Let's Encrypt certificates became valid at approximately 19:29 UTC. Thus this local archive is not evidence of a post-migration Nginx/Certbot recovery set. Do not blindly enable the old timer; verify what the newer off-site recovery-set job actually collects.
- On 2026-10-30 the off-site job logged four new recovery-set completions at 20:19, 20:21, 20:54 and 21:19 UTC; the latest reported `Recovery set complete: 20261030T211925.555690Z bytes: 1402955` and `Offsite snapshot: cb709afa...`. The journal also reported `Restic full data check passed` at 21:19:38 UTC. These are stronger evidence that snapshots exist and a check ran than service exit status alone; **snapshot content coverage, the check command actually run and an isolated restore are still unverified**.
- The current `certbot.timer` uses `authenticator = webroot` with `webroot_path = /var/lib/letsencrypt` for all five names. Confirm Nginx serves the ACME challenge path from this webroot on port 80, and verify actual unattended renewal plus reload hook before calling renewal proven.

- Follow-up read-only inspection of systemd units found `maxzolotoy-offsite-backup.service` invokes `/usr/local/sbin/maxzolotoy-offsite-backup`, which last exited successfully at 2026-10-30 21:19 UTC. `maxzolotoy-config-backup.service` invokes `/usr/local/sbin/maxzolotoy-config-backup`, but had no recorded invocation (`start_time=[n/a]`). The contents of the new off-site script are **not yet reviewed**; successful recovery-set logs are not proof that all Nginx/Certbot/site/systemd files are included.
- A later `sudo nginx -T` inspection showed explicit `location ^~ /.well-known/acme-challenge/ { root /var/lib/letsencrypt; ... }` for **all five HTTP hostnames**. The earlier negative grep result was incomplete (the effective configuration includes the directives). This establishes configured ACME routing, **not** successful public ACME challenge validation or a future automatic certificate renewal.

- The latest local recovery directory, `/var/backups/site-recovery/20261030T211925.555690Z/`, contains `recovery.tar.gz` (1,402,955 bytes), `manifest.json` (2,113 bytes), `systemd-unit-states.txt` (23,756 bytes), and `packages.tsv` (18,235 bytes). Earlier local recovery directories were created at 20:19, 20:21 and 20:54 UTC. Package inventory appears in the two newest directories only. The data proves these files exist locally; **archive contents, manifest semantics, local file permissions, secret exposure and off-site fidelity are unverified**.
- The recovery implementation uses `/usr/local/sbin/site-recovery.py` with functions named `local`, `restic`, `offsite`, `rotate`, `lock` and references to both site backup paths. Function names and path references are evidence of intended design, **not** evidence that both sites, nginx/TLS configuration or certificates are actually covered. A local tarball may contain plaintext secrets even when the remote Restic repository is encrypted.

### Latest local recovery archive verification (owner output, 2026-10-31)

- `/var/backups/site-recovery/20261030T211925.555690Z/recovery.tar.gz`: 1,402,955 compressed bytes; 426 regular archive files totaling 4,180,077 uncompressed bytes. Archive-member classification found Nginx (15), Let's Encrypt (39), systemd (17), local system scripts (10), `maxzolotoy` site (37), `zolotoy-dev-production` (219), firewall (13), SSH config (14) and **zero regular files under `/var/www/zolotoy-dev/` staging**. These category totals may overlap and do not count symlinks; they are not a complete restore validation.
- The local recovery-set directory has `0700` permissions; its four listed artifacts (`recovery.tar.gz`, `manifest.json`, `packages.tsv`, `systemd-unit-states.txt`) are owned by root and have `0600` permissions. This restricts conventional discretionary access to local backups, which may contain private keys.
- The manifest has keys `bytes`, `created`, `excludes`, `parent_directories`, `paths`, `schema`, `sha256`, `sites`; no contents or checksums have yet been validated against a recovered archive.
- A read-only `gzip -t` verification of this exact local `recovery.tar.gz` returned **PASS**. Archive enumeration confirms `var/www/maxzolotoy/`: **37 regular files and 1 symlink**; `var/www/zolotoy-dev-production/`: **219 regular files and 1 symlink**; `var/www/zolotoy-dev/` (staging): **0 files, 0 symlinks, 0 directories**. This checks compressed-stream integrity and entry presence only; symlink destinations, manifest SHA-256, exact content, and isolated extraction remain unverified.
- Investigate whether staging is intentionally excluded and fully reproducible by the existing frontend staging workflow, including its active `current` symlink and Nginx route. Prioritize independent **off-site Restic snapshot discovery, read-only listing and a separate-directory restore**; no changes to production symlinks or runtime services.

### Recovery implementation review (owner-supplied source excerpt, 2026-10-31)

The observed `site-recovery.py` lines 125–210 confirm:

- `offsite()` builds a **new local recovery set**, checks its SHA-256 against the manifest, then runs Restic `backup --json --tag site-recovery-v1` on the **recovery-set root** plus `/var/backups/maxzolotoy` and `/var/backups/zolotoy-dev-production`. It parses the resulting snapshot ID and records success only when that ID exists; local rotation occurs afterward.
- `rotate()` validates each existing local recovery set's schema, tarball length and SHA-256 before deleting oldest completed sets beyond the retained 14; legacy backup archives are not deleted by this function.
- `restic(*args)` starts a subprocess that sources `/root/.config/restic/maxzolotoy.env` without tracing, then executes `restic -o s3.bucket-lookup=dns -o s3.region=ru-1` using the passed arguments. The wrapper itself must never be copied into a public example with actual environment contents.
- `check` calls `restic check --read-data`, consistent with journal lines reporting a full data check. The code uses the `/run/lock/site-recovery.lock` lock in `main()`.
- This confirms meaningful operational guardrails and **what is uploaded**, but not a complete disaster-recovery rehearsal. Backup scope inside `local()` requires additional review (its body was not supplied); staging is absent from the inspected recovery archive.

**Isolated remote restore acceptance test: PASSED, operator-reported 2026-10-31.** On the current VPS, Restic discovered the exact snapshot `cb709afa632b3cc78616c28f91dfadfc0b385235a503f9db73ed780e7b6fc03e` with tag `site-recovery-v1`. An isolated `restic restore` of `/var/backups/site-recovery/20261030T211925.555690Z` to a temporary `/var/tmp` directory reported `PASS`: all four required files restored, `recovery.tar.gz` matched the restored manifest SHA-256 and the original local manifest SHA-256, byte count matched, and `gzip -t` passed. The test script exited successfully and reported temporary-directory cleanup. No production paths, Nginx services or DNS were intentionally modified. These findings are based on output supplied by the operator; no independent remote inspection was performed.

**Proven scope:** the encrypted off-site Restic repository was accessible **from the original host using its existing credentials**, the named remote snapshot was retrievable, and the four-file recovery set was internally consistent after extraction into a temporary directory. **Unproven:** clean-host bootstrap and secret retrieval after loss of the original VPS; tarball extraction/installation with all file permissions and symlink targets; actual serving of both restored websites; staging recreation; successful unattended Certbot renewal; GitHub Actions deployment against a replacement host; DNS cutover and rollback. Removing a temporary directory is not a cryptographic erasure guarantee. Do not restore into `/`, modify production `current` links or run `restic forget/prune` during a rehearsal.

Before claiming portability, verify the active Certbot renewal definitions/schedule, a non-disruptive renewal test when authorized, backup job inputs and latest off-site snapshots, and a restoration to an isolated destination.

Next acceptance priorities: prove the Restic repository URL, repository password and S3 access
credentials can be retrieved securely from outside the original VPS without posting them to GitHub;
perform a clean-host bootstrap and restore rehearsal with both production websites and staging;
verify Certbot unattended renewal, public HTTPS/DNS, CI/CD deployment and rollback. Do not publish
unredacted configuration, credential files, or private keys.

The existing 1 GiB/10 GiB host is suitable only for the currently observed lightweight web
workloads without a measured capacity assessment. Do **not** assume it can host Kafka, PostgreSQL,
Redis, monitoring and four Go services simultaneously. Size a replacement based on real needs.

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
