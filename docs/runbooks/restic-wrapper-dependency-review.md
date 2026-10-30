# Restic backup wrapper dependency review — protected offline evidence

Status (2026-10-31): **read-only static inspector, synthetic CI tests and
an operator-confirmed audit of the real protected Selectel archive**.
The inspection passed its narrow file metadata checks. No wrapper scripts,
Restic commands or production services were executed by this tool. It is
not a replacement-VPS rehearsal.

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

## Real protected archive — operator-reported result (2026-10-31)

The owner ran `review_backup_wrappers.py` on Recovery Set
`20261030T211925.555690Z`, from CI-passing commit
`adff16c4640708df3d6681082c9a7c4462193a4d`.
Observed read-only output:

- `archive_sha256_and_structure: pass-metadata-only`
- `wrapper_file_metadata_checks_pass: true`
- All **three** allowlisted script members were regular, readable, executable,
  root-owned and not group/world writable. Interpreters:
  `offsite_backup=posix-shell`, `restic_check=posix-shell`,
  `site_recovery=python3`.
- Both shell wrappers lexically mention `site-recovery.py`. The check wrapper
  also lexically mentions a check operation. The Python script lexically
  mentions Restic, a Restic environment filename, locking, snapshot/check
  operations and deletion/rotation-related tokens. These are **textual
  indicators only**, not verified commands or a call graph.
- `restic_credential_env_file_in_archive: false`. The known Restic
  environment path is **not packaged as a regular file** in this Recovery Set.
  This may be an intentional secret-exclusion policy. It must NOT be
  interpreted as a missing/failed backup without separate secret custody
  evidence.
- `wrapper_behavior_or_runtime_verified: false`,
  `separate_off_host_s3_and_restic_credentials_verified: false`,
  `safe_to_run_or_restore_without_manual_review: false`; exit code 0.

**Critical independent-recovery gap:** The operator demonstrated the encrypted
offsite snapshot is retrievable **from the original server using its existing
credentials**, not independently from a different environment. A total server
loss also removes access to any Restic password or S3 key stored exclusively
under /root. Before a clean-host rehearsal, establish that both independent
credential sets are securely recoverable, without committing or printing them.

**Next safe evidence:** Check existence, non-symlink type, owner/mode of the
live credential environment file **without opening it**, and compare the three
live wrapper files against their exact archived copies using digests only.
Do not print hashes, source text, command lines or environment variable
values. A matching script copy is evidence of snapshot fidelity, but does not
prove execution correctness or a successful restore.

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
