#!/usr/bin/env python3
"""Read-only, redacted backup-wrapper dependency inventory from a protected Recovery Set.

Only reads three explicitly allowlisted scripts from a SHA-256-verified archive.
Never executes scripts, Restic, systemctl, shells, or network commands; never prints
script bodies, command lines, environment variable values, keys, or S3 locations.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
from pathlib import Path
from typing import Any

from recovery_archive import RecoveryError, verify_set

SCRIPTS = {
    "offsite_backup": "usr/local/sbin/maxzolotoy-offsite-backup",
    "restic_check": "usr/local/sbin/maxzolotoy-restic-check",
    "site_recovery": "usr/local/sbin/site-recovery.py",
}
# This is an exact, known *filename*, not a request to read/output credentials.
CREDENTIAL_ENV_ARCHIVE_PATH = "root/.config/restic/maxzolotoy.env"
MAX_SCRIPT_BYTES = 256 * 1024
SHEBANGS = {
    "/bin/sh": "posix-shell",
    "/usr/bin/sh": "posix-shell",
    "/bin/bash": "bash",
    "/usr/bin/bash": "bash",
    "/usr/bin/env bash": "bash",
    "/usr/bin/env python3": "python3",
    "/usr/bin/python3": "python3",
}
INDICATORS = {
    # Lexical matches only, not proof of executed control flow. Do not output
    # captured values or arbitrary paths (they might include secrets).
    "mentions_site_recovery": r"(?<![A-Za-z0-9_.-])site-recovery\.py(?![A-Za-z0-9_.-])",
    "mentions_restic": r"(?<![A-Za-z0-9_.-])restic(?![A-Za-z0-9_.-])",
    "mentions_restic_env_filename": r"maxzolotoy\.env",
    "mentions_repository_env_key": r"\bRESTIC_REPOSITORY\b",
    "mentions_password_env_key": r"\bRESTIC_PASSWORD(?:_FILE|_COMMAND)?\b",
    "mentions_aws_credential_key": r"\bAWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)\b",
    "mentions_snapshot_operation": r"\b(?:backup|snapshots|restore)\b",
    "mentions_integrity_check": r"\b(?:check|read-data)\b",
    "mentions_removal_or_prune": r"\b(?:prune|forget|rm|shutil\.rmtree|unlink)\b",
    "mentions_locking": r"\b(?:flock|lock|fcntl)\b",
}


def script_text(archive: tarfile.TarFile, member: tarfile.TarInfo) -> str | None:
    """Bounded data read; never reveal payload or decode exceptions."""
    if not member.isfile() or member.size < 0 or member.size > MAX_SCRIPT_BYTES:
        return None
    source = archive.extractfile(member)
    if source is None:
        return None
    with source:
        body = source.read(MAX_SCRIPT_BYTES + 1)
    if len(body) > MAX_SCRIPT_BYTES or b"\x00" in body:
        return None
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return None


def interpreter_category(text: str | None) -> str:
    if not text:
        return "unreadable-or-empty"
    first = text.splitlines()[0].strip()
    if not first.startswith("#!"):
        return "no-shebang"
    return SHEBANGS.get(first[2:].strip(), "unrecognized-shebang")


def lexical_indicators(text: str | None) -> dict[str, bool]:
    """Ignore full-line comments, then only emit fixed-key booleans."""
    if text is None:
        return {key: False for key in INDICATORS}
    noncomment = "\n".join(
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    return {
        key: bool(re.search(pattern, noncomment, flags=re.IGNORECASE))
        for key, pattern in INDICATORS.items()
    }


def review(recovery_set: Path) -> dict[str, Any]:
    # Metadata-only allows historic absolute systemd links as inventory data.
    # It cannot authorize extraction. SHA-256, tar paths/types/limits are verified.
    records, _ = verify_set(recovery_set, metadata_only=True)
    members = {name: member for member, name in records}
    items: dict[str, Any] = {}
    with tarfile.open(recovery_set / "recovery.tar.gz", "r:gz") as archive:
        for label, name in SCRIPTS.items():
            member = members.get(name)
            is_regular = bool(member and member.isfile())
            text = script_text(archive, member) if is_regular else None
            items[label] = {
                "archived_regular_file": is_regular,
                "root_owned": bool(
                    is_regular and member.uid == 0 and member.gid == 0
                ),
                "not_group_or_world_writable": bool(
                    is_regular and not (member.mode & 0o022)
                ),
                "executable_bit": bool(
                    is_regular and (member.mode & 0o111)
                ),
                "bounded_utf8_source_readable": text is not None,
                "interpreter": interpreter_category(text),
                "lexical_indicators": lexical_indicators(text),
            }
    wrapper_files_pass = all(
        item["archived_regular_file"]
        and item["root_owned"]
        and item["not_group_or_world_writable"]
        and item["executable_bit"]
        and item["bounded_utf8_source_readable"]
        for item in items.values()
    )
    return {
        "schema": 1,
        "mode": "backup-wrapper-offline-read-only",
        "archive_sha256_and_structure": "pass-metadata-only",
        "archive_symlinks_validated_for_extraction": False,
        "wrapper_file_metadata_checks_pass": wrapper_files_pass,
        "wrappers": items,
        "restic_credential_env_file_in_archive": bool(
            members.get(CREDENTIAL_ENV_ARCHIVE_PATH)
            and members[CREDENTIAL_ENV_ARCHIVE_PATH].isfile()
        ),
        "separate_off_host_s3_and_restic_credentials_verified": False,
        "wrapper_behavior_or_runtime_verified": False,
        "safe_to_run_or_restore_without_manual_review": False,
        "unverified": [
            "wrapper-commands-arguments-and-control-flow",
            "wrapper-sourced-files-and-imports",
            "restic-password-and-s3-credentials-outside-original-vps",
            "restic-repository-provisioning-and-read-write-access",
            "lock-retention-and-destructive-side-effects",
            "successful-new-host-backup-and-isolated-restore",
        ],
        "note": (
            "Indicator values are lexical presence only; false does not prove "
            "absence, and true does not prove the code executes"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recovery_set", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(review(args.recovery_set), sort_keys=True, indent=2))
        return 0
    except (RecoveryError, OSError, ValueError, tarfile.TarError, EOFError):
        print("Backup wrapper review refused (invalid/unreadable input)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
