# Independent Restic S3 access check from macOS

Status (2026-10-31): **runbook prepared, not yet operator-tested on Mac**.
The owner reported that the existing Restic decryption password was saved
outside the Selectel VPS in a password manager, and that S3 keys are available.
No independent S3 access or off-host restore is confirmed yet.

This test must run **in the local Mac Terminal**, with no VPN/SSH tunnel
to the source VPS and no reliance on source-VPS credential files.

## Source of the exact repository address

Do not guess the S3 bucket name, endpoint or optional Restic path prefix.
Use the existing `RESTIC_REPOSITORY` value from the original private backup
configuration, or securely maintained independent infrastructure records.
Do not paste that URL into a public issue. The original VPS backup wrapper
has used `-o s3.bucket-lookup=dns` and `-o s3.region=ru-1`.
The Selectel S3 pool endpoint is pool-specific; this fact does not identify
the user's bucket or the Restic prefix.

## Installation

On macOS with Homebrew, run `brew install restic` (or check
`restic version` if already installed). Restic docs and Homebrew both
document this installation. Do not upgrade the original server's Restic
merely because a newer CLI runs on macOS.

## Gate 1: no-lock / no-cache snapshot discovery

**Never** run `init`, `backup`, `forget`, `prune`, `unlock`,
`repair` or `key` while performing this access-only test.
Only list snapshots with `--no-lock`; no repository lock/write is needed.
Prefer a separate S3 credential with read-only rights when available.
Existing write-capable keys are an operational risk if the operator later
runs a destructive command, even though this script does not.

Paste into a trusted local Mac terminal (not an SSH session). The script
prompts secrets through /dev/tty with disabled echo, inside a child Bash
process. Do not log, paste into chat, or capture the live credentials.

~~~bash
bash <<'BASH'
set -uo pipefail
set +x
umask 077

if ! command -v restic >/dev/null 2>&1; then
  printf 'STOP: install restic with brew install restic\n'
  exit 1
fi

printf 'Exact RESTIC_REPOSITORY (s3:...): ' > /dev/tty
IFS= read -r RESTIC_REPOSITORY </dev/tty
case "$RESTIC_REPOSITORY" in
  s3:*) ;;
  *) printf 'STOP: expected an S3 repository URL\n'; exit 1 ;;
esac

printf 'Selectel S3 Access Key ID (hidden): ' > /dev/tty
IFS= read -r -s AWS_ACCESS_KEY_ID </dev/tty
printf '\n' > /dev/tty
printf 'Selectel S3 Secret Key (hidden): ' > /dev/tty
IFS= read -r -s AWS_SECRET_ACCESS_KEY </dev/tty
printf '\n' > /dev/tty
printf 'Existing Restic password (hidden): ' > /dev/tty
IFS= read -r -s RESTIC_PASSWORD </dev/tty
printf '\n' > /dev/tty

if [[ -z "$RESTIC_REPOSITORY" || -z "$AWS_ACCESS_KEY_ID" ||
      -z "$AWS_SECRET_ACCESS_KEY" || -z "$RESTIC_PASSWORD" ]]; then
  printf 'STOP: one or more required inputs are empty\n'
  exit 1
fi

export RESTIC_REPOSITORY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY RESTIC_PASSWORD
export AWS_DEFAULT_REGION='ru-1'
python3 - <<'PY'
import json
import os
import subprocess

target = "cb709afa632b3cc78616c28f91dfadfc0b385235a503f9db73ed780e7b6fc03e"
cmd = [
    "restic", "--no-cache", "--no-lock",
    "-o", "s3.bucket-lookup=dns",
    "-o", "s3.region=ru-1",
    "snapshots", "--json",
]
try:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
except subprocess.TimeoutExpired:
    print("STATUS: connection timed out")
    raise SystemExit(2)

if proc.returncode != 0:
    error = proc.stderr.lower()
    if proc.returncode == 12 or "wrong password" in error:
        reason = "wrong Restic password or incompatible repository key"
    elif "accessdenied" in error or "access denied" in error or "403" in error:
        reason = "S3 access denied / permissions"
    elif proc.returncode == 10 or "does not exist" in error or "not found" in error:
        reason = "repository URL, bucket, prefix or endpoint not found"
    else:
        reason = "connection/configuration failed (details intentionally withheld)"
    print("STATUS: FAIL —", reason)
    raise SystemExit(2)

try:
    snapshots = json.loads(proc.stdout)
    assert isinstance(snapshots, list)
    found = any(
        isinstance(item, dict) and item.get("id") == target
        for item in snapshots
    )
except (ValueError, AssertionError, TypeError):
    print("STATUS: FAIL — unrecognized snapshot JSON")
    raise SystemExit(2)

print("STATUS: repository decrypted and snapshots read from Mac")
print("Target protected snapshot present:", found)
print("Ready for isolated restore step:", found)
raise SystemExit(0 if found else 3)
PY
status=$?
unset RESTIC_PASSWORD AWS_SECRET_ACCESS_KEY AWS_ACCESS_KEY_ID RESTIC_REPOSITORY AWS_DEFAULT_REGION
printf 'Independent access-test exit code: %s\n' "$status"
exit "$status"
BASH
~~~

A successful result for the **specific target snapshot** proves access to
encrypted repository metadata with independently entered credentials while
the source VPS was not used for the test. It does **not** prove all data packs
can be downloaded/decrypted or that the website works on a replacement VPS.

The script suppresses potentially identifying errors/URLs rather than
logging raw Restic stderr. If it fails, classify before troubleshooting;
never paste secret-bearing output. Secrets exist temporarily in the local
child shell environment and Restic process memory, not in shell history.
Using a trusted Mac without terminal recording/debug tracing is necessary.

## Gate 2: protected isolated restore (after Gate 1 succeeds)

Do not begin a local restore until the snapshot was independently confirmed
and the owner approved the destination. The four-file Recovery Set may
contain root keys/private certificates **inside** `recovery.tar.gz`.
On macOS, choose an encrypted disk/APFS volume with exclusive user access,
create a new directory mode 0700, restore only the exact Recovery Set to
that directory with `--no-lock`, confirm manifest size/SHA-256,
and remove it securely or retain it in protected storage per owner policy.
Never extract the tarball to / or restore live service paths. Never commit
the tarball or upload it to ChatGPT or GitHub.

## Evidence and remaining gates

Record **only** the redacted success/failure Booleans and command exit code
in the infrastructure PR. After an independent isolated restore is proven,
still review external symlink resolution, packages, Nginx, Certbot private
key handling, systemd dependencies, deployments and rollback on a disposable
new server. No production DNS/service changes, Restic prune, credential
rotation or PR merging is authorized by this runbook.
