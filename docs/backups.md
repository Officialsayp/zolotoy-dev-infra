# Backup and restore plan

Status (2026-10-31): operator-confirmed **independent Mac-to-Selectel S3
snapshot access and four-file Recovery Set restore**, with SHA-256, byte
length and GZIP integrity checks PASS. This test required no connection to the
source VPS. **This is not a clean-host or cross-provider website rebuild.**
The owner has deferred replacement-VPS testing until a second host exists.

## Confirmed website recovery baseline (owner-supplied evidence)

- The existing `/usr/local/sbin/site-recovery.py` creates a manifest-protected local recovery
  set and uploads the recovery-set root plus `/var/backups/maxzolotoy` and
  `/var/backups/zolotoy-dev-production` to encrypted Restic storage in Selectel S3
  (region `ru-1`), tagged `site-recovery-v1`. The job records a confirmed snapshot ID and
  retains up to 14 locally verified recovery sets.
- A 2026-10-30 21:19 UTC recovery set contains an archive, JSON manifest, package inventory
  and systemd unit state inventory. The archive includes files in Nginx, Let's Encrypt,
  systemd, system-script, firewall, SSH and both **production** site paths.
  It does **not** include the `/var/www/zolotoy-dev/` staging tree.
- Local backups are root-owned (directory `0700`; individual recovery files `0600`);
  treat local unencrypted tarballs as sensitive, even when remote Restic storage is encrypted.
- On 2026-10-31 the owner ran an **isolated recovery from named Restic snapshot**
  `cb709afa632b3cc78616c28f91dfadfc0b385235a503f9db73ed780e7b6fc03e`
  into a temporary directory: all four required files were recovered, the archive
  SHA-256 matched both local and restored manifests, the compressed-stream integrity
  check passed, and the temporary test directory was removed.
- The underlying `restic check --read-data` reported success on 2026-10-30.
  This validates much more than backup-job exit status, but **does not prove**
  recoverability when the original VPS and its credential file no longer exist.
- Frontend staging has a separate existing manual main-branch workflow,
  `zolotoy-dev-frontend/.github/workflows/deploy-selectel-staging.yml`, which
  packages a verified build and deploys under `/var/www/zolotoy-dev/releases`
  with active-Nginx preflight and rollback. Recovery can rebuild staging from Git
  *only when* SSH keys, GitHub Environment variables, correct Nginx modules/routes,
  site directories, user permissions and public TLS have been re-established.
  A successful staging redeploy on a replacement host is **not yet tested**.

For exact restore scope, evidence qualifications and migration order, see
[portable VPS recovery runbook](runbooks/portable-vps-migration.md).

## Critical dependency: secrets must survive loss of the VPS

The current script sources `/root/.config/restic/maxzolotoy.env`. Do not assume that
this file can be retrieved after the VPS is destroyed. Verify **independently and out
of band** that an authorized operator can access, without relying on the old VPS:

1. Restic repository location, repository decryption password and required S3
   access credentials (plus the documented recovery process if keys are rotated);
2. provider console access, verified SSH host-key enrollment process, and the
   GitHub Environment deployment credential rotation/rebinding procedure;
3. DNS/CDN administrator access, current DNS zone export, domain registration
   access, and a way to issue/restore trusted TLS before a `.dev` cutover;
4. the required account/SSH/sudo configuration and any other **non-reconstructable**
   application secrets.

Store these in an appropriate encrypted password manager or vault with an
off-host recovery route and independent access control. **Never copy passwords,
private keys, certificates containing private keys, token values or raw secret
environment files into GitHub, CI artifacts, chat or ordinary documentation.**
Document existence, owner and recovery path, not secret values. Do not claim this
requirement is satisfied merely because secrets exist on the VPS.

## Future backend data (not yet deployed)

No verified production PostgreSQL/Kafka/Redis state or backend image deployment
exists at the observed baseline. When real backend state is deployed, require:

- service-owned PostgreSQL consistent database backups and documented restore order;
- infrastructure configuration and secrets available via independent secure recovery;
- selected durable state not reconstructable from source systems;
- explicit Kafka consumer/outbox consistency checks when event processing is introduced.

Redis cache is generally reconstructable and cannot be treated as the sole durable
copy. Kafka retention cannot replace consistent database backups. Do not turn
hypothetical backend components into invented running services.

## Evidence and next-stage priorities without a second VPS

**Passed (operator evidence, 2026-10-31):** independent Mac access to
encrypted Restic metadata, exact snapshot discovery and isolated retrieval of
all four protected Recovery Set files. The restored tarball SHA-256 and byte
count matched its manifest; streaming GZIP check passed. The Mac's temporary
restore folder was removed. The actual archive contents were not extracted
into a live filesystem. See
[independent macOS Restic restore](runbooks/independent-macos-restic-restore.md).

**Current-vps priorities:** inspect the real backup-check and offsite-backup
timer states/last results, local Recovery Set freshness, disk headroom, public
TLS renewal schedule and evidence, and whether there is a supported offsite
retention policy. Do these as bounded, read-only status checks; do not activate
timers, run backup/check jobs, prune or delete snapshots without separate
review. See [operational check](runbooks/current-vps-operational-check.md).

**Deferred — no second VPS available or authorized:** clean Ubuntu rebuild,
full tar symlink classification for staging, Nginx/Certbot/systemd restore,
both websites and staging end-to-end smoke tests, GitHub deployment to
replacement host, controlled DNS cutover and rollback. These remain
**unverified**, not passed or waived. They can resume when a disposable host
is available, without modifying production.

**Still open on the existing VPS:** observed unattended Certbot renewal,
non-disruptive deploy/release retention and locking alignment with existing
GitHub Actions, backup cadence monitoring and S3 retention monitoring.
No automatic deletion should be implemented as part of a read-only audit.

## Pre-deploy rule

Any migration that can make rollback unsafe requires a backup/restore assessment
before production deployment. Never use `docker compose down -v` or delete
stateful data as part of routine rollback. Do not promise automatic rollback
across incompatible schema migrations.
