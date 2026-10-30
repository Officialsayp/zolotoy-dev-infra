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
The tool checks archive SHA-256 and **read-only metadata safety** (including
allowing absolute/external symlinks as archived *data*, never as extraction
instructions), reads only small allowlisted configuration fragments in memory,
and emits a bounded JSON summary. The report field
`recovery_archive_hash_and_structure` is `pass-metadata-only`, not proof
that the archive can be safely extracted.
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

## Read-only acceptance check against the *actual* Recovery Set

This check has **not** been executed by the repository maintainer or CI against
the protected Selectel archive. The original VPS is not accessible to the
GitHub connector, and uploading the real backup to GitHub Actions would risk
disclosing TLS private keys. Do **not** attach or commit the tarball.

An operator with authorized root access to the existing host can run the
following in a **trusted local checkout at a reviewed full commit SHA**, without
changing website configuration or unarchiving private keys:

```bash
# From a trusted copy of Officialsayp/zolotoy-dev-infra on the original VPS.
# The operator must verify the checkout's full SHA against the reviewed PR.
git rev-parse HEAD
sudo python3 -B scripts/recovery_archive.py \
  /var/backups/site-recovery/20261030T211925.555690Z \
  --metadata-only
sudo python3 -B scripts/review_certbot_systemd.py \
  /var/backups/site-recovery/20261030T211925.555690Z
```

The two `python3 -B` processes read the local recovery archive, manifest and
selected metadata. No `--stage-dir`, `--apply`, `--rollback-journal`,
network access, service reload, or Restic write is requested. `-B` disables
bytecode cache writes. Running `sudo` can still produce ordinary host
authentication/audit records; this is not a zero-side-effect process at the
operating-system level.

Expected review fields include `recovery_archive_hash_and_structure: pass-metadata-only`,
`known_scope_checks_pass`, `static_review_complete`,
`safe_to_apply_without_further_review: false`, plus per-domain and per-unit
Booleans. `static_review_complete: false` is presently expected because the
exact Restic-check service `ExecStart` has not been confirmed. Any additional
false or missing values should be classified, **not** auto-corrected on the
production VPS. Save only the redacted report or paste the summarized JSON
after personally checking it for sensitive content.

This runs checks against the original host's *local copy*. It does **not**
replace the previously demonstrated isolated Restic **remote** restore, nor
does it establish clean-host portability or successful future unattended ACME
renewal.

## Compact read-only report for missing checks

If the full JSON report is too long, use this option from an already-verified
repository checkout. It prints **only** false known-scope checks and
unresolved dependencies, with no archived config contents, private key bytes,
or ExecStart values:

```bash
python3 -B scripts/review_certbot_systemd.py \
  /var/backups/site-recovery/20261030T211925.555690Z \
  --failures-only
```

A successful process exit means the report was generated; it does **not**
mean all checks passed. When `known_scope_checks_pass` is false, inspect
`failed_known_checks`. The separate `unresolved_manual_reviews` list
contains unknown facts (such as the Restic-check ExecStart) and is **not**
silently interpreted as a failed script.

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
