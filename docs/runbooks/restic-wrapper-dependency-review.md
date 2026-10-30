# Restic backup wrapper dependency review — protected offline evidence

Status (2026-10-31): **read-only static inspector and synthetic CI tests**.
The new script has not been run against the real Selectel recovery archive or
tested on a replacement VPS. It does not execute or install any archive scripts.

## Confirmed context

The original Selectel VPS has production websites served by Nginx and a
protected four-file Recovery Set. The owner has confirmed the recovery set's
SHA-256 and size, performed an isolated restore from encrypted Restic storage,
and passed a narrow real-archive static Certbot/systemd inspection.

Three candidate script paths in the Recovery Set are known; the new inspector must still verify each archived file's owner and mode:

- /usr/local/sbin/maxzolotoy-offsite-backup
- /usr/local/sbin/maxzolotoy-restic-check
- /usr/local/sbin/site-recovery.py

The archived restic-check systemd unit matched the live unit byte-for-byte;
it directly invokes /usr/local/sbin/maxzolotoy-restic-check. This identifies
an executable, **not its contents or runtime effects**. The previously
identified Restic environment path is /root/.config/restic/maxzolotoy.env.
Independent, off-original-host access to those secrets is not yet proven.

## Read-only command

From a checkout locked to an operator-reviewed full commit SHA, on a protected
host with legitimate read access to the Recovery Set:

    python3 -B scripts/review_backup_wrappers.py \
      /var/backups/site-recovery/20261030T211925.555690Z

The tool verifies the recovery archive SHA-256 and safe member paths/types
in metadata-only mode, then reads only the three exact allowlisted script
members, each bounded to 256 KiB, in memory. It produces a fixed-key JSON
report with file presence, root ownership, group/world-write restrictions,
executable bit, interpreter category and **lexical Boolean indicators** for
possible references to Restic, a recovery wrapper, credential variable
names, backup/check operations, locking and destructive operations.

It never prints the script contents, arbitrary source paths, command
arguments, private values, credentials or S3 locations. It never reads the
contents of the Restic environment file. It does not run Restic, systemctl,
scripts, shells, ACME or network operations, and cannot perform staging,
installation, migration, secret recovery or backup writes.

The indicators are **not a parser, call graph or behavioral proof**.
A match can occur in unreachable code or a string, and indirect/dynamic
dependencies can be missed. A true wrapper_file_metadata_checks_pass means
only that the three archived file identities, permissions and bounded
readability passed. It does NOT mean a backup can be restored.

Every report explicitly sets:
- wrapper_behavior_or_runtime_verified = false
- separate_off_host_s3_and_restic_credentials_verified = false
- safe_to_run_or_restore_without_manual_review = false

## Off-host credential recovery must be proven separately

Surviving loss of the original VPS requires independent access to the matching
Restic repository password, S3 credentials, correct bucket/endpoint/region,
a recovery-scoped least-privilege IAM policy, and a protected way to provision
the new root-only credential file. Presence of a 0600 credential file on
the original VPS proves local access controls only.

NEVER commit, upload, print, paste or put plaintext credentials/private keys
in GitHub, an Actions artifact, a public log or this review report.
A compromised source VPS may require credential and certificate rotation.

## Remaining independently approved gates

1. The owner runs the new read-only inspector on the genuine Recovery Set
   and provides only its redacted JSON.
2. Actual contents of all three backup scripts, called helpers,
   environment-loading logic, runtime binaries, locks, network access,
   error handling, retention and delete/prune behavior are reviewed privately.
3. Independently recover S3/Restic credentials, then perform a **read-only**
   snapshot discovery and protected isolated restore without the source VPS.
4. Only after explicit separate approval: rehearse new-host backup writes,
   protected TLS restore/renewal, timer activation, sites/deployments and
   DNS cutover with tested rollback. Do not run prune/forget or alter the
   original VPS as part of this offline review.

See the [Certbot/systemd review](certbot-systemd-recovery.md),
[Recovery Set staging](recovery-archive-staging.md) and
[portable disaster recovery](portable-vps-migration.md).
