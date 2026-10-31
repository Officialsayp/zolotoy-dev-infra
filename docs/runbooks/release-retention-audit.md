# Read-only release retention audit — 3 independent site deployment layouts

Status (2026-10-31): GitHub deployment sources and read-only VPS output reviewed.
The existing `site-releases-prune.timer` is enabled; the corresponding service
last ran successfully on 2026-10-25 in `--apply` mode. Its journal contains no
`DELETE:` entries, so the evidence does not demonstrate any release deletion.
This review authorizes neither additional deletion nor changes to the live timer.

## Confirmed from the source repositories

**maxzolotoy.com — Officialsayp/saypix**:
`.github/workflows/deploy-direct-origin.yml` uses
`/var/www/maxzolotoy/releases/<commit SHA>`, with the active
`/var/www/maxzolotoy/current` symlink. Atomic activation uses
`/var/www/maxzolotoy/releases/.deploy-maxzolotoy.lock` plus flock.
Its in-workflow deploy stage does not implement broad old-release pruning.
The existing VPS release-prune timer and its successful execution are now
confirmed by owner-supplied `systemctl` and `journalctl` output. Its service
reported `Deployment lock: ACQUIRED`; exact on-server lock path and deployment
compatibility require a complete script/unit inspection before modifications.

**zolotoy.dev production — Officialsayp/zolotoy-dev-frontend**:
`scripts/selectel/production-remote.py` uses
`/var/www/zolotoy-dev-production/releases/<SHA>-<run>-<attempt>/site`,
`/var/www/zolotoy-dev-production/current`, and the lock
`/var/www/zolotoy-dev-production/releases/.deploy-production.lock`.
It includes an explicit manifest-verified rollback transaction.
`docs/deployment/SELECTEL_PRODUCTION.md` historically says old
releases are retained and no release pruning occurs before a separate
retention policy is approved. That source description is now stale relative
to the confirmed active VPS prune timer; reconcile it before changing behavior.

**zolotoy.dev staging — Officialsayp/zolotoy-dev-frontend**:
`scripts/selectel/remote.sh` uses
`/var/www/zolotoy-dev/releases/current`, a lock at
`/var/www/zolotoy-dev/releases/.deploy.lock`, release directories,
paired `.metadata-<release ID>` directories, and possibly
`.incoming-<release ID>` upload directories.
`docs/deployment/SELECTEL_STAGING.md` documents rollback and
preservation of old and failed candidates. Metadata is not disposable
merely because it starts with a dot.

**Important:** all three lock filenames, users, release naming schemes,
active-link locations and rollback semantics differ. Do not deploy a
generic `find -mtime -delete` or one shared global pruning service.
The existence of a lockfile does not prove no deployment is currently
running. The existing cleanup reports successful lock acquisition for both
production sites, but full lock path matching to each CI deploy workflow was
not independently established by the supplied truncated script output.
Do not add, change or manually trigger cleanup on the strength of this audit.

## Owner-run operator inventory — no deletion and no remote job trigger

Run directly on the existing Selectel VPS under an authorized SSH session.
The code reads only **top-level metadata** for three known roots, does
not recursively inspect release contents or print release identifiers,
and will not modify `current`, lockfiles, release directories or timers.

~~~bash
(
  set -euo pipefail
  python3 -B - <<'PY'
import json
import os
import re
import stat
from pathlib import Path

layouts = {
    "maxzolotoy": (
        Path("/var/www/maxzolotoy"),
        "releases", "current", ".deploy-maxzolotoy.lock", "sha",
    ),
    "zolotoy_production": (
        Path("/var/www/zolotoy-dev-production"),
        "releases", "current", ".deploy-production.lock", "prod",
    ),
    "zolotoy_staging": (
        Path("/var/www/zolotoy-dev"),
        "releases", "releases/current", ".deploy.lock", "staging",
    ),
}
patterns = {
    "sha": re.compile(r"^[0-9a-f]{40}$"),
    "prod": re.compile(r"^(?:[0-9a-f]{40}-[0-9]+-[0-9]+|prod-[0-9]{8}T[0-9]{6}Z-[0-9a-f]+)$"),
    "staging": re.compile(r"^[0-9a-f]{40}-[0-9]+-[0-9]+$"),
}

def kind(path):
    try:
        mode = path.lstat().st_mode
    except (OSError, ValueError):
        return "missing-or-unreadable"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "regular"
    return "other"

result = {}
for label, (base, release_name, current_name, lock_name, layout) in layouts.items():
    releases = base / release_name
    current = base / current_name
    lock = releases / lock_name
    inventory = {
        "release_root": kind(releases),
        "current": kind(current),
        "lock_file": kind(lock),
        "current_target_inside_release_root": False,
        "current_points_to_expected_layout": False,
        "top_level_release_directories": 0,
        "unrecognized_directories": 0,
        "metadata_directories": 0,
        "incoming_directories": 0,
        "other_entries": 0,
    }
    if inventory["release_root"] == "directory":
        if inventory["current"] == "symlink":
            try:
                resolved = current.resolve(strict=True)
                relative = resolved.relative_to(releases.resolve(strict=True))
                parts = relative.parts
                valid = (
                    len(parts) == 2 and parts[1] == "site"
                    if layout == "prod"
                    else len(parts) == 1
                )
                inventory["current_target_inside_release_root"] = True
                inventory["current_points_to_expected_layout"] = bool(
                    valid and patterns[layout].fullmatch(parts[0])
                    and kind(resolved) == "directory"
                )
            except (OSError, RuntimeError, ValueError):
                pass
        try:
            with os.scandir(releases) as entries:
                for item in entries:
                    name = item.name
                    if name in (lock_name, "current"):
                        continue
                    if item.is_dir(follow_symlinks=False):
                        if patterns[layout].fullmatch(name):
                            inventory["top_level_release_directories"] += 1
                        elif name.startswith(".metadata-") and layout == "staging":
                            inventory["metadata_directories"] += 1
                        elif name.startswith(".incoming-"):
                            inventory["incoming_directories"] += 1
                        else:
                            inventory["unrecognized_directories"] += 1
                    else:
                        inventory["other_entries"] += 1
        except OSError:
            inventory["listing_failed"] = True
    result[label] = inventory

print("=== RELEASE INVENTORY — NO DELETION ===")
print(json.dumps({
    "sites": result,
    "current_symlinks_changed": False,
    "lockfiles_modified": False,
    "releases_deleted": False,
    "automatic_cleanup_authorized": False,
}, indent=2, sort_keys=True))
PY
)
echo "Diagnostic exit code: $?"
echo "=== SSH SESSION STILL ACTIVE ==="
~~~

A release directory count says nothing about space used: this tool does
not recursively calculate sizes to avoid slow scans of production content.
The checker is read-only and does not acquire deployment locks, so its
observation is a point-in-time, potentially racing snapshot. A previously
archived older release or currently active release must **never** be
deleted merely because a count exceeds a retention target.

## Observed production retention and remaining safety conditions

Owner-supplied 2026-10-31 evidence:
- Old `maxzolotoy-release-cleanup.timer`: `disabled`; new
  `site-releases-prune.timer`: `enabled`, with its next scheduled run on
  2026-11-01 around 04:20 UTC.
- Successful 2026-10-25 `--apply` journal: both production sites reported
  `Deployment lock: ACQUIRED`, one protected release each, `KEEP NEWEST: 5`,
  and `MINIMUM AGE: 30 days`; no `DELETE:` messages appeared.
- The script excerpt also checks protected release IDs, symlink pointers,
  filesystem change-time age and rechecks `current` before removal.
- Counts on 2026-10-25 were 10 `maxzolotoy` and 6 `zolotoy.dev production`
  release directories. The later read-only inventory counted 17 and 9,
  respectively, with valid `current` pointers. Staging had one release,
  plus one `.incoming-*` and one `.metadata-*` directory (both timestamped
  2026-10-18); staging is not covered by the observed two-site prune log.
- A successful `--apply` run with no deletion is **not** a demonstrated safe
  deletion, rollback rehearsal, or permission for additional removal.

Before modifying existing cleanup, extending it to staging, or approving
additional deletion, confirm:
1. Actual on-server inventory, active symlinks and root ownership.
2. At least an explicitly chosen rollback set per site, not an ungrounded
   generic count; protect active release and any release referenced by
   pending in-flight transactions or an approved rollback tag.
3. Exact release-lock compatibility *and lock acquisition* for cleanup.
4. Corresponding staging metadata pairs, interrupted incoming directory
   policy, release integrity manifests and GitHub deployment concurrency.
5. Recovery availability and rollback test for each site, with a separately
   approved dry-run of planned deletions; then a distinct authorization
   before automatic deletion.

Do not confuse **local release retention** with Restic **S3 snapshot
retention**. Restic forget/prune, even with a retention policy, would
alter shared offsite storage and is not part of this procedure.

See [production operational monitoring](current-vps-operational-check.md),
[portable restore gates](portable-vps-migration.md) and
[backup policy](../backups.md).
