# Certbot and systemd recovery — offline evidence and approval gates

Status (2026-10-31): **read-only offline code + synthetic CI tests**. No application to
live VPS, production certificates, actual backup or clean replacement host has occurred.

The observed Selectel site host now uses **Nginx + Certbot**, not the older Caddy +
lego model. The archive may contain root-only TLS secrets. Never copy the entire
archive to / or print private keys, account credentials or raw unit contents.

## Static inspection — no installation

From a trusted operator checkout, after an independently validated offsite Recovery
Set is fetched into a protected local directory:

    python3 scripts/review_certbot_systemd.py /secure/recovery/20261030T211925.555690Z

Replace the example directory with the actual protected recovery-set path.
The tool checks the archive SHA-256 and safe member structure, reads only small
allowlisted configuration fragments in memory, and emits a bounded JSON summary.
It never outputs raw renewal settings, service ExecStart contents or certificate
material. It cannot install or enable any service or contact Let's Encrypt.

Checks include:
- Five named renewal profiles for both sites (including their www/origin names);
  the archived webroot authenticator and expected /var/lib/letsencrypt webroot.
- Presence of live certificate/fullchain/private-key paths, without reading keys.
- Presence, archived owner/mode, executable bit, POSIX syntax and expected
  guarded nginx syntax-check/reload lines in the deploy hook.
- Presence of the two expected backup-service/timer pairs, service ExecStart
  directives and schedule directives. Only the off-site backup wrapper path has
  been confirmed from operator-supplied source evidence; the Restic-check
  service's exact ExecStart remains **unknown** and must not be guessed. The
  report therefore marks that execution contract as requiring manual review.
- Presence (not full cryptographic verification) of separately saved package and
  systemd-state inventories.

**A complete static review is not proof of a successful renewal or restoration.**
The report distinguishes known_scope_checks_pass from static_review_complete.
Because the actual Restic-check service ExecStart has not been established,
static_review_complete remains false until the execution contract is reviewed
separately. The report always sets safe_to_apply_without_further_review to false.
The hook check also requires the *entire* expected six-line shell program,
including set -eu, not merely isolated matching commands.
Some unit names and backup script paths are based on earlier owner-provided
observations and must be reconciled with the actual recovered unit definitions.
A missing member is a gap for review, not permission to fabricate one.

## Controlled Certbot restoration — separate operator approval required

1. Independently recover the Restic password, S3 credentials and DNS control
   outside the source VPS; confirm the intended new host and security boundary.
2. Review the actual Nginx HTTP-01 challenge routing and package versions.
   Valid HTTPS and trusted SAN coverage are mandatory before .dev DNS cutover.
3. Choose between properly authorized secure recovery of prior certificate
   material and fresh issuance. If keys may be compromised, do not transplant
   them. HTTP-01 may fail while DNS points to the old VPS; a reviewed DNS-01
   flow is an alternative where technically supported.
4. If restoring keys, validate the entire certificate chain, key pairing,
   account/renewal file permissions, symlink destinations and exact paths.
   The private staging helper uses restrictive temporary modes, not the original
   deployment permissions. Never commit real PEM files or credentials.
5. Only after a separately reviewed Nginx/TLS installation, validate nginx -t,
   local hostname-specific trusted HTTPS, Certbot timer configuration and
   deploy-hook execution/renewal through supervised checks. Observing an actual
   automatic renewal remains a further acceptance gate.

The observed legacy zolotoy-dev-certificate.timer (lego) was **disabled**.
Do not enable it, adopt obsolete Caddy Automatic HTTPS instructions or trigger
production reissuance as part of this preparation. Preserve the known-good
certificates and configs outside public repositories for a documented rollback.

## Controlled systemd restoration — separate operator approval required

The observed operational services are maxzolotoy-offsite-backup.service and
maxzolotoy-restic-check.service, with companion timers. The old
maxzolotoy-config-backup.timer was disabled. The new archive contains scripts,
but archive presence does not establish dependencies, security, enabled state,
or the correct files for a new Ubuntu package version.

On a disposable new VPS only, an operator must:
- review the exact unit and wrapper scripts, ExecStart, EnvironmentFile, User,
  lock locations, service permissions, runtime hardening and dependencies;
- compare packaged Certbot systemd units to the installed package, rather
  than blindly restoring obsolete ones;
- retain protected previous unit/scripts and enabled-state inventory;
- explicitly authorize each file installation, daemon-reload and timer
  start/enable operation separately after syntax checks;
- verify remote Restic repository isolation/retention before any new backup write
  and prove a new backup plus isolated restore before declaring operational success.

A rollback must disable only newly introduced timers before restoring reviewed
prior units and their exact enabled-state inventory. Never delete/prune the
original Restic snapshots during a rehearsal, and never modify the current VPS.

## Offline CI

    python3 -m unittest discover -s tests -p 'test_*.py' -v
    python3 -m py_compile scripts/review_certbot_systemd.py

All tests are synthetic and cannot prove a production renewal or live disaster
recovery. For full stage order and operator STOP points see
[portable VPS recovery](portable-vps-migration.md),
[private archive staging](recovery-archive-staging.md), and
[guarded Nginx recovery](nginx-reviewed-restore.md).
