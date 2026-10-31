# Current Selectel VPS — read-only operational resilience audit

**Scope (2026-10-31):** owner has **deferred all replacement-VPS
rehearsal work** until an independent test host is available. Independent
Mac-side S3/Restic access, protected four-file Recovery Set retrieval, archive
SHA-256/size and GZIP validation have already passed. This check is about
the **ongoing production-host schedule and recoverability**, not a second
disaster recovery test.

## Operating constraints

- Do not restart or reload Nginx, Certbot, Restic or systemd.
- Do not call `restic backup/check/forget/prune/unlock` or alter S3 settings.
- Do not activate/disable timers or adjust retention/deployment scripts.
- Do not print `Environment`, `ExecStart`, full journals, URLs or secret values.
- Service state `inactive` can be normal for an exited oneshot task. Check
  `Result`, `ExecMainStatus` and the **timestamp** together; a past
  `Result=success` is not proof of a fresh successful execution.
- This script does not claim any S3 snapshot freshness; local backup age,
  systemd timer last/next trigger, and remote object retention are distinct.

## Status-only diagnostic on the original VPS

Run the following from the existing trusted SSH session (it leaves the shell
open, makes no modifications to services, and does not run backup jobs):

~~~bash
(
  set -euo pipefail
  python3 -B - <<'PY'
import json
import shutil
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

units = (
    "maxzolotoy-offsite-backup.timer",
    "maxzolotoy-offsite-backup.service",
    "maxzolotoy-restic-check.timer",
    "maxzolotoy-restic-check.service",
    "certbot.timer",
    "certbot.service",
)
fields = (
    "LoadState", "ActiveState", "UnitFileState", "Result",
    "ExecMainStatus", "ExecMainExitTimestamp",
    "LastTriggerUSec", "NextElapseUSecRealtime",
)
result = {}
for unit in units:
    try:
        proc = subprocess.run(
            ["systemctl", "show", "--no-pager",
             "--property=" + ",".join(fields), unit],
            capture_output=True, text=True, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        result[unit] = {"readable": False}
        continue
    raw = dict(
        line.split("=", 1) for line in proc.stdout.splitlines()
        if "=" in line and line.split("=", 1)[0] in fields
    )
    result[unit] = {
        "readable": proc.returncode == 0,
        **{key: raw.get(key, "unknown") for key in fields},
    }

base = Path("/var/backups/site-recovery")
ages = []
try:
    for child in base.iterdir():
        if not stat.S_ISDIR(child.lstat().st_mode):
            continue
        manifest = child / "manifest.json"
        if manifest.is_symlink():
            continue
        try:
            meta = manifest.stat()
            if stat.S_ISREG(meta.st_mode):
                ages.append(meta.st_mtime)
        except OSError:
            continue
except (OSError, PermissionError):
    pass

now = datetime.now(timezone.utc).timestamp()
usage = shutil.disk_usage("/")

print("=== VPS OPERATIONS — READ-ONLY ===")
print(json.dumps({
    "systemd": result,
    "local_recovery_sets_with_manifest": len(ages),
    "newest_local_manifest_age_hours": (
        round(max(0, now - max(ages)) / 3600, 2)
        if ages else None
    ),
    "root_disk_free_gib": round(usage.free / 2**30, 2),
    "root_disk_used_percent": round(usage.used / usage.total * 100, 1),
    "offsite_snapshot_freshness_verified": False,
    "automatic_tls_renewal_verified": False,
    "s3_retention_policy_verified": False,
    "production_changes_performed": False,
}, sort_keys=True, indent=2))
print("=== READ-ONLY AUDIT COMPLETE ===")
PY
)
echo "Audit exit code: $?"
echo "=== SSH SESSION STILL ACTIVE ==="
~~~

The status report is deliberately bounded and prints no private file
contents, journal entries, unit command lines, S3 repositories or
credentials. The `manifest.json` modification time provides a local
**freshness hint** only; it does not prove that the manifest or its corresponding
offsite snapshot is valid. It is a metadata query, not backup creation.

## Operator result on existing Selectel VPS (2026-10-31)

The owner ran the read-only operational diagnostic over the six service/timer
units. Reported `Diagnostic exit code: 0`, SSH stayed open, and
`production_changes: false`.

- Root filesystem: **5.62 GiB free**, **38.1% used** at observation time.
- Four local directories with a regular `manifest.json`; the newest manifest
  modification time was about **3.03 hours** before inspection. File mtime
  alone does not demonstrate S3 snapshot freshness or complete backup health.
- All three timers were `loaded`, `enabled` and `active`.
- `maxzolotoy-offsite-backup.timer`: last reported trigger
  **2026-10-30 01:30:15 UTC**; next planned trigger
  **2026-10-31 01:42:42 UTC**. Its oneshot service last reported successful
  completion at **2026-10-30 21:19:28 UTC** with `ExecMainStatus=0`.
  The latter does not prove timer-triggered execution because these times differ.
- `maxzolotoy-restic-check.timer`: last reported trigger
  **2026-10-25 03:04:05 UTC**; next
  **2026-11-01 03:26:51 UTC**. Its service reported a successful exit at
  **2026-10-30 21:19:38 UTC**; this may be separate from the weekly trigger.
- `certbot.timer`: enabled and active, with next scheduled trigger
  **2026-10-31 04:32:14 UTC**; no last trigger timestamp in the report.
  `certbot.service` showed `Result=success`/`ExecMainStatus=0`
  but no actual `ExecMainExitTimestamp`, therefore no automatic renewal
  or even a completed timer invocation was established.

**Current assessment:** no low-disk condition or service failure is shown
by this limited output. The two backup services' last successful *exits*
are positive but distinct from successful *scheduled runs* and actual
fresh remote snapshot state. We should observe the next scheduled
offsite timer, the next Certbot timer, and the next integrity timer
without manually triggering, restarting, changing units or performing
a renewal. A timer run still does not guarantee successful certificate
issuance; assess that separately using renewal status/certificate expiry.
S3 retention and latest remote snapshot age have not been verified.

## Interpretation and next operator gates

1. Confirm both actual backup-related timers are enabled/active, and compare
   their last trigger and configured next trigger. If a timer does not appear,
   do **not** auto-enable it; establish intent and actual scheduling first.
2. Separate `maxzolotoy-offsite-backup.service` exit evidence from
   `maxzolotoy-restic-check.service` exit evidence. Neither alone proves
   remote snapshot integrity.
3. Check disk headroom and apparent local Recovery Set age against the owner-
   agreed backup cadence. Previous evidence suggested up to 14 locally
   verified Recovery Sets; **there is no approved S3 retention policy yet**.
4. Certbot timer being active is not actual unattended renewal. The five
   known certificates were previously observed with expiry 2027-01-28;
   preserve the existing TLS monitoring until automatic renewal is observed.
5. For deployment release cleanup, review the actual saypix and zolotoy.dev
   GitHub Actions concurrency locks, active `current` links, rollback
   requirements, and any cleanup script *before* proposing auto-deletion.
   An initial source review has documented three different lock schemes,
   rollback layouts and a safe inventory command in
   [the release retention audit](release-retention-audit.md).
   Keep the original host untouched during this review.
6. Once a separate test VPS is available, resume the postponed isolated
   symlink/host restoration, deploy, TLS, DNS and rollback rehearsal. That
   milestone is **deferred**, never marked passed.

See [backup evidence](../backups.md), [portable VPS recovery](portable-vps-migration.md),
and [independent Mac Restic recovery](independent-macos-restic-restore.md).
