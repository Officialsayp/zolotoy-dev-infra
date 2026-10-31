# Verified recovery archive — offline inspection and private staging

Status (2026-10-31): **synthetic offline CI tests** plus an independently
successful Mac-side download of the real four-file Recovery Set with
SHA-256/GZIP verification. The inner archive remains unsafe to stage due to
unresolved symlinks. Owner has **deferred all replacement-VPS deployment
steps** until a second host is available; this is not a waiver of the gate.
The staging script has not been run against the actual protected tarball.
This procedure does NOT automatically make an existing website live.

## Why another stage exists

Restic restores the four-file `site-recovery` recovery set from Selectel S3,
and the previously tested local GZIP/SHA-256 checks prove archive transfer
integrity. The new standalone
[recovery inspector](../../scripts/recovery_archive.py) adds **defensive
archive metadata checks before any attempted extraction**. It supports a
manifest verification and an optional **private staging-only extraction**.

It deliberately cannot:

- fetch S3 credentials or restore a Restic snapshot for you;
- write Nginx, Certbot, SSH, systemd or website configurations into their live paths;
- enable a timer, start/reload a service or change DNS;
- copy production TLS/private keys or GitHub SSH credentials into a repository;
- guarantee the restored version is appropriate for a new OS/package set.

The live 2026-10-30 recovery set included both production sites and their
`current` symlinks, but **no staging files**. Staging must be reproducible
through the separate, manually gated frontend GitHub workflow.

## First: verify metadata without writing

After separately restoring a four-file Recovery Set from a verified off-site
Restic snapshot into a **private temporary directory**, run locally:

```bash
python3 scripts/recovery_archive.py \
  /secure/staging/20261030T211925.555690Z
```

The example path is illustrative; replace with the *actual* private path.
Only a manifest SHA-256 check, archive metadata scan, counts and integrity
constraints run; the script prints **no archive file contents, key material
or detailed member names**.

The manifest must have `schema=1`, a SHA-256 hexadecimal digest and a
matching compressed byte count. The inspector rejects duplicate members,
absolute or parent-traversing paths, hardlinks, special files, unsafe
symlinks (including targets outside the extracted set), entries nested
under files/symlinks, and archives exceeding conservative size/count
limits. Symlinks such as Let's Encrypt's relative links into
`../../archive` are permitted **only when they resolve inside the archive**.

## When strict validation fails on an absolute symlink

The **2026-10-31 real recovery archive** passed manifest schema, compressed-size
and SHA-256 checks on the original Selectel VPS, but the strict metadata
validator returned `Unsafe absolute or malformed symlink`. This is **not
evidence of archive corruption**: source host symlinks may legitimately use
absolute paths that would escape an isolated extraction root.

Do **not** loosen the extraction rule or stage this archive yet. Instead,
from a trusted checkout that matches the reviewed PR commit, run:

```bash
python3 -B scripts/recovery_archive.py \
  /var/backups/site-recovery/20261030T211925.555690Z \
  --diagnose-symlinks
```

The diagnostic rechecks the manifest SHA-256 before reading archive headers
and emits **aggregate counts only**, grouped by the symlink's source area
(Nginx, Let's Encrypt, systemd, website or other). The target classes
distinguish absolute targets *present elsewhere in the archive*, external
absolute targets, relative targets, malformed targets and traversal. It
does not print source filenames, symlink destination strings or file content.
It never enables extraction, and its `archive_safe_for_staging` result
remains `false` unconditionally.

An absolute link with a target represented inside the archive may be a
candidate for **separate, explicitly reviewed relative-link rewriting**, but
this is not yet implemented. External absolute links require manual analysis
and must not be blindly replicated inside a private staging directory.
The original strict `verify_set` and `--stage-dir` paths continue to reject
all absolute symlinks.

## Operator-supplied real archive symlink inventory (2026-10-31)

The operator ran the aggregate-only diagnostic against the exact protected
Recovery Set. Reported: **681 archive entries and 112 symbolic links**; SHA-256
and compressed length matched the manifest. There were **zero malformed member
names**. The symlinks broke down as:

- 22 relative targets represented inside the archived tree;
- 6 absolute targets represented in the archive;
- 83 absolute targets **not represented in the archive**;
- 1 relative target not represented in the archive.

**79 of the 83 external absolute link targets originate in systemd**, with 3
from Nginx and 1 elsewhere. This may be normal systemd enablement linking to
package-managed unit files, but it is **not proof** those targets are available
or correct on a replacement VPS. Do not misclassify all 83 as damaged or treat
them as safe to extract.

### Separate read-only metadata verification from extraction

The original strict `verify_set` still rejects absolute and unresolved links,
because extracting those links unchanged could escape a private staging root.
The newer command below allows their presence **only as archival metadata**:

```bash
python3 -B scripts/recovery_archive.py \
  /var/backups/site-recovery/20261030T211925.555690Z \
  --metadata-only
```

It verifies the manifest SHA-256, archive size, member paths, duplicate paths,
types, member count, expanded-size limits, and file/symlink parent safety. It
does **not** certify the symlink target, issue a restore approval, or extract
anything. Output must explicitly include `safe_to_stage: false`. Tests ensure
that handing metadata-only records to the staging function cannot bypass the
strict link guard.

The separate `review_certbot_systemd.py` inspector now calls metadata-only
verification to read selected configuration evidence safely. It will still
return `safe_to_apply_without_further_review: false`. Running both scripts
against the protected real archive is a **read-only acceptance test**, not a
clean-host disaster-recovery rehearsal.

## Second: optional private staging on a NEW isolated host

Only if there is a concrete recovery need and protected local storage,
run:

```bash
python3 scripts/recovery_archive.py \
  /secure/staging/20261030T211925.555690Z \
  --stage-dir /var/tmp/recovery-reviewed-20261030 \
  --acknowledge-sensitive-data
```

The staging destination must be a **nonexistent absolute path** under
`/tmp` or `/var/tmp`. A failed stage removes only the newly created
temporary staging directory; source archives are unchanged. All staged
regular files get mode `0600`, directories `0700`; original owners and
modes are **not installed**, and their original preservation requires a
separate reviewed restore procedure. Symlinks are created last after
validation. This directory **may contain plaintext private keys or other
secrets**; maintain host encryption, root-only access where applicable,
and remove it securely once no longer needed. Removing the folder does
not guarantee forensic erasure on all storage media.

Do not stage on the currently active VPS just to demonstrate this feature:
the first goal is code review and synthetic CI validation. Never point the
destination at `/`, `/etc`, `/var/www` or any production release tree.
No `tar -xf -C /` or recursive `cp` is an approved restore operation.

## Local and CI checks

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m py_compile scripts/recovery_archive.py
```

Tests use temporary synthetic archives. They cover checksum validation,
valid site and Let's Encrypt relative symlinks, private staging and
malicious tar entries without touching S3, real secrets or the VPS.

## Clean-host acceptance gates still missing

1. Obtain Restic S3 credentials and its repository password independently
   of the old VPS, using a secure off-host recovery process.
2. Recreate verified package/module/deploy-user baseline on a **disposable**
   Ubuntu server using the separate guarded Ansible playbook.
3. Restore the selected snapshot into an isolated directory, inspect its
   reviewed configuration, file ownership, symlink targets and secret policies.
   Only then install active site configuration under separate authorization.
4. Confirm both production sites, staging rebuild, Nginx/Certbot TLS,
   GitHub Actions deployments and rollback before any DNS cutover.

See [web VPS Ansible bootstrap](web-vps-bootstrap.md) and
[portable VPS migration runbook](portable-vps-migration.md).
