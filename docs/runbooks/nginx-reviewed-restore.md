# Reviewed Nginx configuration restore — clean host only

Status: **Python synthetic tests in CI; not yet tested on an actual replacement VPS**.
This is a guarded second phase after the [Ubuntu baseline](web-vps-bootstrap.md)
and [private archive staging](recovery-archive-staging.md).

## Why installation is separate

The reviewed 2026-10-31 Selectel VPS runs Nginx, njs, headers-more, Certbot and
Restic. A recovery archive includes both production sites, TLS directories and
systemd units, but **restoring all archive files directly to "/" would be unsafe**.
Names, permissions, versions, secrets, symlink behavior, service dependencies,
firewall rules and existing files must be reviewed on the replacement host.

The [Nginx configuration tool](../../scripts/restore_nginx.py) only supports
**regular non-key files under \`etc/nginx/\`** from an *already validated and
privately staged* recovery archive. **Other configuration remains separate**:

- Let's Encrypt/Certbot certificates, private keys, renewal configs and webroot:
  follow the [offline Certbot/systemd recovery review](certbot-systemd-recovery.md)
  before manual authorized secret recovery and version-aware installation; never
  export PEM keys in GitHub or CI artifacts.
- systemd units/timers and firewall configuration: review actual dependencies,
  permissions and command paths before a separate, approved installation.
  The Nginx tool cannot install/enable any service or timer.
- site release trees: use the existing verified website deploy/restore workflows;
  do not copy production symlinks blindly.
- \`/etc/nginx/sites-enabled/*\` may contain *symbolic links*. This tool excludes
  symlinks; an authorized operator must review and recreate required links.
  The tool does not remove stale default Nginx sites or restore include files
  outside \`etc/nginx/\`.
- The existing private \`/root/.config/restic/maxzolotoy.env\` must be recovered
  out of band; do not read it from GitHub, logs or an untrusted channel.

## Step 1: read-only inventory and approval plan

Use a trusted terminal on a **new isolated VPS**, after validating a recovery set
and staging its archive under an operator-controlled \`0700\` temporary directory.
For example (replace this illustrative path with the actual private location):

\`\`\`bash
python3 scripts/restore_nginx.py \
  --stage /var/tmp/recovery-reviewed-20261030
\`\`\`

This prints a JSON **candidate** list of regular Nginx files and SHA-256 hashes.
It **does not mean all candidates should be installed**. Independently review
each file's actual contents *only in a secure trusted operator session*; compare
it with the active repository Nginx/njs profile and the new OS packages.
Eliminate stale Caddy-era references, unknown \`include\` directives, credentials,
unexpected proxy destinations and duplicate virtual hosts.

Save a selected, reviewed JSON file locally **outside Git**, for example:

\`\`\`json
{
  "schema": 1,
  "files": [
    {
      "path": "etc/nginx/nginx.conf",
      "sha256": "<the actual reviewed 64-hex-digit SHA-256>"
    }
  ]
}
\`\`\`

This is a **format example**, not a real, verified digest. Record only actual
hashes emitted by the inventory command after verifying the exact file bytes.
Keep the plan in a protected directory; do not commit production-specific
configurations or secret values to the repository.

Validate the selection **without modifying Nginx**:

\`\`\`bash
python3 scripts/restore_nginx.py \
  --stage /var/tmp/recovery-reviewed-20261030 \
  --plan /secure/recovery/nginx-reviewed.json
\`\`\`

The inspector requires exact SHA-256 matches and refuses duplicated, oversized,
unexpected, symlinked, traversal, hidden, private-key and out-of-scope files.

## Step 2: explicitly authorized pre-cutover installation

The apply command below is an **operational write and must NOT be run on the
existing Selectel VPS**. Only an authorized operator may use it after the
new/empty host, inventory, verified backup and rollback procedure are reviewed.

Prerequisites:

1. The original production and staging \`current\` pointers do **not** exist
   on the new host. Any such pointer aborts installation (including a dangling
   symlink). This is a safety belt, not a universal live-host detector.
2. The selected Nginx configuration has been reviewed against the installed
   module versions, expected DNS hostnames and recovered TLS file paths.
3. Every destination's parent directory already exists and is not a symlink.
   Non-file source/target entries are refused. Rebuild missing directories
   using an approved, separate step.
4. The new host has a valid nonsecret baseline and \`/usr/sbin/nginx\`.
   Missing TLS certificate material can make \`nginx -t\` fail; configure
   that sensitive material separately. The installer rolls back on such failure.
5. \`/var/backups/site-recovery\` exists, is root-only, and has sufficient
   capacity to hold the current Nginx config versions.
6. SSH access, host identity and provider console access are verified separately.

\`\`\`bash
sudo python3 scripts/restore_nginx.py \
  --stage /var/tmp/recovery-reviewed-20261030 \
  --plan /secure/recovery/nginx-reviewed.json \
  --apply \
  --confirm-host "$(hostname)"
\`\`\`

The script acquires a local exclusive lock, checks all files before changes,
makes root-only copies of existing Nginx files plus a JSON rollback journal in
\`/var/backups/site-recovery/nginx-review-*\`, atomically installs only the
explicitly listed files as mode \`0644\`, and runs \`nginx -t\`.

If \`nginx -t\` fails, it attempts to revert modified files and remove
newly created files. On a successful check, it prints the protected journal
path. **It does not reload Nginx** or activate websites/DNS. A crash/power loss
mid-transaction still requires manual inspection; rollback is not an
uninterruptible database transaction.

## Step 3: optional pre-cutover rollback

Before any site release is activated (no \`current\` pointers), the operator
may explicitly restore prior Nginx files. Use the journal path printed by
a successful apply, NOT a guessed path:

\`\`\`bash
sudo python3 scripts/restore_nginx.py \
  --rollback-journal /var/backups/site-recovery/nginx-review-REVIEWED-ID \
  --confirm-host "$(hostname)"
\`\`\`

The rollback checks the currently installed files against the exact hashes
from the original reviewed plan, and validates the rolled-back Nginx config.
It refuses to overwrite intervening edits or run after the site pointers exist.
If rolled-back syntax validation fails, it attempts to reinstall the candidate
configuration and aborts. This stage does **not** reload or restart Nginx.
Preserve the root-only journal until the replacement host has passed all
restoration, smoke and rollback tests.

## Remaining clean-host restore stages

This tool intentionally does not claim to complete a VPS reconstruction.
The remaining phases are separate, explicitly approved work:

1. Independently recover and install Let's Encrypt private material and ACME
   account/renewal settings; verify Certbot paths and executable reload-hook.
2. Review and restore necessary systemd unit files/scripts; only later enable
   required timers after dependency and secret validation.
3. Install and verify Nginx include symlinks, check \`nginx -t\`, and activate
   the restored configuration only under an approved, rollback-ready operation.
4. Rebuild both production website releases and \`origin.zolotoy.dev\` staging.
5. Test real external TLS, CI/CD, off-site backup jobs, restoration, and rollback
   on the replacement host before any DNS cutover.

Run synthetic checks without touching the VPS:

\`\`\`bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m py_compile scripts/restore_nginx.py
\`\`\`

Source of recovery evidence:
[portable VPS recovery runbook](portable-vps-migration.md).
