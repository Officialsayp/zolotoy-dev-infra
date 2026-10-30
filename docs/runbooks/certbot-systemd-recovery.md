# Certbot and systemd recovery — offline evidence and approval gates

Status (2026-10-31): **synthetic CI tests and operator-confirmed real-backup
static inspection passed** for the bounded Certbot/systemd evidence checks.
The owner ran the read-only inspector on the live VPS against the protected
local Recovery Set; no production configurations were installed or changed.
An independent clean-host recovery has NOT been rehearsed.

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
  Certbot supports either `webroot_path` (sometimes a comma-terminated
  ConfigObj list) or a per-domain `[[webroot_map]]` under `[renewalparams]`.
  For a given domain, a map entry takes precedence. The inspector accepts
  only one unambiguous effective matching root and exposes only the source
  category and Boolean match, never the raw renewal path.
- Presence of live certificate/fullchain/private-key paths, without reading keys.
- Presence, archived owner/mode, executable bit, POSIX syntax and expected
  guarded nginx syntax-check/reload lines in the deploy hook.
- Presence of the two expected backup-service/timer pairs and their schedules.
  Owner-supplied read-only inspection confirmed the `maxzolotoy-restic-check`
  service's direct executable is `/usr/local/sbin/maxzolotoy-restic-check`.
  The exact archived/live service file matched byte-for-byte, and the wrapper
  is in the archive, root-owned, and executable. The updated inspector checks
  that specific executable path (not substring presence), regular-file type,
  ownership, non-writable permissions and executable bit. Any extra ExecStart
  arguments remain subject to separate manual review; wrapper *contents* and
  runtime dependencies are not validated by this narrow check.
- Presence (not full cryptographic verification) of separately saved package and
  systemd-state inventories.

**A complete static review is not proof of a successful renewal or restoration.**
The report distinguishes known_scope_checks_pass from static_review_complete.
The Restic-check executable path is now established from an archived unit
matching the live unit. `static_review_complete` may become `true` if the
allowlisted checks pass and no unreviewed ExecStart arguments remain. This
does **not** mean the wrapper's internal commands, environment, backup
credentials, external packages or network operations were validated.
The report always sets `safe_to_apply_without_further_review` to `false`.
The hook check also requires the *entire* expected six-line shell program,
including set -eu, not merely isolated matching commands.
Some unit names and backup script paths are based on earlier owner-provided
observations and must be reconciled with the actual recovered unit definitions.
A missing member is a gap for review, not permission to fabricate one.

## Read-only acceptance check against the *actual* Recovery Set

The owner **has executed this read-only check successfully** against the
protected Selectel archive on the original VPS. The repository maintainer and
CI cannot independently inspect that server's protected archive: results
below rely on the operator-provided terminal output. Uploading the real backup
to GitHub Actions would risk disclosing TLS private keys. **Do not** attach
or commit the tarball.

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
Booleans. The Restic-check service's direct executable has now been
identified by the owner. Any unexpected `ExecStart` arguments or other
failed/unknown fields should be classified, **not** auto-corrected on the
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
`failed_known_checks`. The `webroot_evidence_sources` object counts which
supported representation was found; it does not expose any actual paths.
The separate `unresolved_manual_reviews` list
contains unknown facts (such as the Restic-check ExecStart) and is **not**
silently interpreted as a failed script.

## Real Recovery Set — webroot compatibility finding (2026-10-31)

An operator ran the read-only inspector against the protected live-host
Recovery Set. All five renewal profiles reported `expected_webroot=false`
while other known-scope checks passed. The old inspector compared only the
literal scalar `webroot_path=/var/lib/letsencrypt`; therefore this is **not
evidence of misconfigured Certbot**. Certbot serializations can include a
trailing comma or a nested per-domain `[[webroot_map]]`. The updated parser
handles both forms, keeps map precedence, and rejects conflicting values.

**Confirmed result:** the owner reran the corrected inspector on the real
archive and all five profiles were recognized as `webroot_map`. The report
contained no remaining failed known checks. This static comparison still does
**not** prove unattended ACME renewal, DNS reachability or correct Nginx
challenge delivery.

## Real systemd unit executable identity (2026-10-31)

The owner inspected the **real SHA-256-matched archive**, without printing the
raw unit or invoking systemd. The archived `maxzolotoy-restic-check.service`
was shown to match the active VPS unit **byte-for-byte** and to have one
`ExecStart`. The extracted executable basename was
`maxzolotoy-restic-check`; the command referred to an absolute archived
`/usr/local/sbin` program with the same name. That archived file was
root-owned and had an executable bit. This resolves the previously unknown
**entry-point identity**, not the script's contents or its behavior.

The inspector now recognizes both observed wrappers. It does not open or
execute the Restic wrapper scripts, evaluate environment variables, prove
Restic credentials are independently recoverable, or verify successful
execution on a clean Ubuntu host. Any `static_review_complete=true`
applies only to the explicitly listed static predicates and does **not**
authorize installation, enabling timers or merging operational changes.

## Final bounded static audit — PASS (operator output, 2026-10-31)

The owner ran `review_certbot_systemd.py --failures-only` from the
CI-reviewed commit `2a72545095111ea8a256c54da546ed26edc9d965`
against the original VPS's protected recovery set
`20261030T211925.555690Z`. The terminal returned:

- `failed_known_checks: []`
- `known_scope_checks_pass: true`
- `static_review_complete: true`
- `unresolved_manual_reviews: []`
- `webroot_evidence_sources`: five `webroot_map`, zero `webroot_path`
  and zero missing
- `recovery_archive_hash_and_structure: pass-metadata-only`
- `safe_to_apply_without_further_review: false`
- process exit code `0`; SSH session remained active

This resolves the previously missing direct executable identity for the
`maxzolotoy-restic-check` unit and the Certbot renewal-config parser
compatibility issue. It proves that the selected archive metadata, file
identities and owner/mode predicates in **this inspector** passed. It does
**not** validate the wrapper script's internal commands, its environment,
private credentials off-host, effective systemd sandboxing, unattended ACME
renewal or any successful clean-host restore.

**Remaining gates:** secure independent off-host S3/Restic credential recovery,
static review of backup wrapper behavior and dependencies, complete
replacement-VPS restore rehearsal (including Nginx, site releases, TLS,
staging rebuild, CI deployment and rollback), and independently observed
unattended Certbot renewal. Strict archive extraction remains blocked by
absolute/external symlinks; no one should infer `safe_to_stage=true` from
the passed metadata-only check.

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
