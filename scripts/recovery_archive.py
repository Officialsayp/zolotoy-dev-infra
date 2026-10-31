#!/usr/bin/env python3
"""Verify an existing site-recovery archive and optionally stage it in /tmp.

Never runs Restic, installs files into /etc or /var/www, switches live releases,
restarts services, handles DNS, or prints secret contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import sys
import tarfile
from collections import Counter
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_MEMBERS = 25000
MAX_SINGLE_FILE = 256 * 1024 * 1024
CHUNK = 1024 * 1024
PATH_GROUPS = {
    "nginx": "etc/nginx/",
    "letsencrypt": "etc/letsencrypt/",
    "systemd": "etc/systemd/",
    "server_scripts": "usr/local/sbin/",
    "maxzolotoy": "var/www/maxzolotoy/",
    "zolotoy_production": "var/www/zolotoy-dev-production/",
    "zolotoy_staging": "var/www/zolotoy-dev/",
}


class RecoveryError(Exception):
    """Unsafe or unverifiable backup input."""


def regular_file(path: Path) -> bool:
    return stat.S_ISREG(path.lstat().st_mode)


def read_manifest(recovery_set: Path) -> dict:
    path = recovery_set / "manifest.json"
    if not regular_file(path) or path.stat().st_size > 1024 * 1024:
        raise RecoveryError("Manifest is missing, non-regular or oversized")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RecoveryError("Invalid manifest structure")
    checksum = value.get("sha256")
    size = value.get("bytes")
    if (value.get("schema") != 1 or not isinstance(size, int)
            or isinstance(size, bool) or size <= 0
            or not isinstance(checksum, str)
            or re.fullmatch(r"[0-9a-f]{64}", checksum) is None):
        raise RecoveryError("Unsupported manifest schema, byte count or checksum")
    return value


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while data := handle.read(CHUNK):
            digest.update(data)
    return digest.hexdigest()


def normalize_path(raw: str) -> str:
    if (not raw or raw.startswith("/") or "\\" in raw
            or "\x00" in raw or ".." in PurePosixPath(raw).parts):
        raise RecoveryError("Unsafe absolute, parent or malformed archive path")
    path = PurePosixPath(raw).as_posix()
    if path in ("", "."):
        return ""
    if path.startswith("../") or path == "..":
        raise RecoveryError("Archive path escapes staging root")
    return path


def resolve_link(name: str, target: str) -> str:
    if not target or target.startswith("/") or "\\" in target or "\x00" in target:
        raise RecoveryError("Unsafe absolute or malformed symlink")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
    if resolved in (".", "..") or resolved.startswith("../") or resolved.startswith("/"):
        raise RecoveryError("Symlink escapes staging root")
    return resolved


def inspect_members(
    archive: Path, *, metadata_only: bool = False
) -> tuple[list[tuple[tarfile.TarInfo, str]], Counter]:
    """Audit tar metadata. Metadata-only mode NEVER validates link targets for extraction.

    A successful metadata-only result means only safe member paths/types/counts:
    absolute, dangling or external symlinks are intentionally NOT extraction-safe.
    """
    if not regular_file(archive) or archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise RecoveryError("Archive missing, non-regular or exceeds safety limit")
    records = []
    paths: set[str] = set()
    kinds: dict[str, str] = {}
    links: dict[str, str] = {}
    expanded = 0
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            if len(records) >= MAX_MEMBERS:
                raise RecoveryError("Too many archive entries")
            name = normalize_path(member.name)
            if not name:
                if not member.isdir():
                    raise RecoveryError("Non-directory archive root")
                continue
            if name in paths:
                raise RecoveryError("Duplicate archive path")
            if member.isfile():
                kind = "file"
                if member.size < 0 or member.size > MAX_SINGLE_FILE:
                    raise RecoveryError("Individual archive file exceeds safety limit")
                expanded += member.size
                if expanded > MAX_EXPANDED_BYTES:
                    raise RecoveryError("Expanded archive exceeds safety limit")
            elif member.isdir():
                kind = "directory"
            elif member.issym():
                kind = "symlink"
                links[name] = member.linkname
            else:
                raise RecoveryError("Hardlinks, devices and special entries are forbidden")
            paths.add(name)
            kinds[name] = kind
            records.append((member, name))

        for name in paths:
            parent = PurePosixPath(name).parent
            while parent.as_posix() != ".":
                parent_name = parent.as_posix()
                if kinds.get(parent_name) in ("file", "symlink"):
                    raise RecoveryError("Archive entry is nested under a file/symlink")
                parent = parent.parent

        # Unsafe absolute/external links are valid inventory *data*, but must
        # continue to block staged extraction. Do not weaken strict mode.
        if not metadata_only:
            for name, link in links.items():
                target = resolve_link(name, link)
                if kinds.get(target) in ("file", "directory"):
                    continue
                if target in links:
                    raise RecoveryError("Chained archive symlink requires manual review")
                if not any(p.startswith(target + "/") for p in paths):
                    raise RecoveryError("Symlink target missing from archive")

    counts = Counter()
    for member, name in records:
        if member.isfile():
            counts["regular_files"] += 1
        elif member.issym():
            counts["symlinks"] += 1
        elif member.isdir():
            counts["directories"] += 1
        for group, prefix in PATH_GROUPS.items():
            if name.startswith(prefix) or name == prefix.rstrip("/"):
                counts[group] += 1
    counts["entries"] = len(records)
    counts["expanded_bytes"] = expanded
    return records, counts


def verify_set(
    directory: Path, *, metadata_only: bool = False
) -> tuple[list[tuple[tarfile.TarInfo, str]], Counter]:
    """Verify archive hash and member safety; metadata-only does not approve extraction."""
    if directory.is_symlink() or not directory.is_dir():
        raise RecoveryError("Recovery-set directory is missing or a symlink")
    manifest = read_manifest(directory)
    archive = directory / "recovery.tar.gz"
    if not regular_file(archive):
        raise RecoveryError("Recovery archive is not a regular file")
    if archive.stat().st_size != manifest["bytes"]:
        raise RecoveryError("Archive length does not match manifest")
    if digest_file(archive) != manifest["sha256"]:
        raise RecoveryError("Archive SHA-256 does not match manifest")
    try:
        return inspect_members(archive, metadata_only=metadata_only)
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise RecoveryError("Archive cannot be fully verified") from exc


def diagnose_symlinks(directory: Path) -> dict:
    """Safe, aggregate-only report; NEVER grants permission to extract.

    Validates the compressed archive hash first, then reads tar headers only.
    Raw member names, link destinations and secret file contents are never printed.
    """
    if directory.is_symlink() or not directory.is_dir():
        raise RecoveryError("Recovery-set directory is missing or a symlink")
    manifest = read_manifest(directory)
    archive = directory / "recovery.tar.gz"
    if not regular_file(archive) or archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise RecoveryError("Archive missing, non-regular or oversized")
    if archive.stat().st_size != manifest["bytes"] or digest_file(archive) != manifest["sha256"]:
        raise RecoveryError("Archive SHA-256/size mismatch")

    members: set[str] = set()
    symlinks: list[tuple[str, str]] = []
    malformed_member_names = 0
    count = 0
    with tarfile.open(archive, "r:gz") as source:
        for entry in source:
            count += 1
            if count > MAX_MEMBERS:
                raise RecoveryError("Too many archive entries")
            try:
                member_name = normalize_path(entry.name)
                if member_name:
                    members.add(member_name)
            except RecoveryError:
                malformed_member_names += 1
            if entry.issym():
                symlinks.append((entry.name, entry.linkname))

    # Existing tar archives often omit explicit directory records.
    # Count a path as present only if a member exists at or below it.
    def in_archive(path: str) -> bool:
        return path in members or any(x.startswith(path + "/") for x in members)

    def scope(name: str) -> str:
        if name.startswith("etc/nginx/"):
            return "nginx"
        if name.startswith("etc/letsencrypt/"):
            return "letsencrypt"
        if name.startswith("etc/systemd/"):
            return "systemd"
        if name.startswith("var/www/"):
            return "website"
        return "other"

    categories: dict[str, Counter] = {}
    overall: Counter = Counter()
    for name, target in symlinks:
        try:
            normalized_name = normalize_path(name)
            name_valid = bool(normalized_name)
        except RecoveryError:
            normalized_name = ""
            name_valid = False

        if not name_valid:
            status = "unsafe_member_name"
        elif not target or "\\" in target or "\x00" in target:
            status = "malformed_target"
        elif target.startswith("/"):
            parts = PurePosixPath(target).parts
            if ".." in parts or target.startswith("//"):
                status = "malformed_absolute_target"
            else:
                resolved = posixpath.normpath(target).lstrip("/")
                status = (
                    "absolute_target_in_archive" if resolved and in_archive(resolved)
                    else "absolute_target_not_in_archive"
                )
        else:
            resolved = posixpath.normpath(
                posixpath.join(posixpath.dirname(normalized_name), target)
            )
            if resolved in (".", "..") or resolved.startswith("../"):
                status = "relative_target_escapes_root"
            else:
                status = (
                    "relative_target_in_archive" if in_archive(resolved)
                    else "relative_target_not_in_archive"
                )
        overall[status] += 1
        group = scope(name)
        categories.setdefault(group, Counter())[status] += 1

    return {
        "schema": 1,
        "mode": "symlink-diagnostics-only",
        "archive_sha256_and_size": "pass",
        "archive_safe_for_staging": False,
        "members_scanned": count,
        "malformed_member_names": malformed_member_names,
        "symlinks_total": len(symlinks),
        "symlink_target_categories": dict(sorted(overall.items())),
        "by_source_group": {
            group: dict(sorted(values.items()))
            for group, values in sorted(categories.items())
        },
        "note": "No extraction or live-path changes; raw link paths/targets withheld",
    }


def validate_stage_target(path: Path) -> Path:
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise RecoveryError("Stage target must be a new, absolute directory")
    parent = path.parent.resolve(strict=True)
    allowed = (Path("/tmp").resolve(), Path("/var/tmp").resolve())
    if not any(parent == base or base in parent.parents for base in allowed):
        raise RecoveryError("Stage target must be below /tmp or /var/tmp")
    return path


def stage(directory: Path, destination: Path, records: list[tuple[tarfile.TarInfo, str]]) -> None:
    target = validate_stage_target(destination)
    # Defense in depth: a caller must never pass metadata-only records to the
    # extraction routine. Always re-run strict link verification independently.
    records, _ = verify_set(directory)
    old_umask = os.umask(0o077)
    created = False
    try:
        target.mkdir(mode=0o700)
        created = True
        with tarfile.open(directory / "recovery.tar.gz", "r:gz") as source:
            # Create everything but symlinks first. All staging files are 0600:
            # original modes/owners must be reviewed during later installation.
            for member, name in records:
                if member.issym():
                    continue
                out = target.joinpath(*PurePosixPath(name).parts)
                if member.isdir():
                    out.mkdir(mode=0o700, parents=True, exist_ok=True)
                    out.chmod(0o700)
                else:
                    out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    with source.extractfile(member) as original, out.open("xb") as saved:
                        if original is None:
                            raise RecoveryError("Archive file missing readable content")
                        shutil.copyfileobj(original, saved, CHUNK)
                    out.chmod(0o600)
                    if out.stat().st_size != member.size:
                        raise RecoveryError("Extracted file length mismatch")
            for member, name in records:
                if member.issym():
                    out = target.joinpath(*PurePosixPath(name).parts)
                    out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    out.symlink_to(member.linkname)
    except BaseException:
        # Clean up ONLY our own successfully created stage directory.
        # A competing process may have created the same path after preflight.
        if created and target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        raise
    finally:
        os.umask(old_umask)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recovery_set", type=Path, help="Directory containing manifest.json and recovery.tar.gz")
    parser.add_argument(
        "--diagnose-symlinks", action="store_true",
        help="Read-only aggregate symlink diagnosis; never approves staging",
    )
    parser.add_argument(
        "--metadata-only", action="store_true",
        help="Verify checksum, member paths/types/limits, but never certify symlinks for extraction",
    )
    parser.add_argument("--stage-dir", type=Path, help="NEW private destination below /tmp or /var/tmp")
    parser.add_argument(
        "--acknowledge-sensitive-data",
        action="store_true",
        help="Required with --stage-dir: restored data may include TLS keys and secrets",
    )
    args = parser.parse_args()
    try:
        if args.diagnose_symlinks or args.metadata_only:
            if args.diagnose_symlinks and args.metadata_only:
                raise RecoveryError("Select one read-only inspection mode")
            if args.stage_dir or args.acknowledge_sensitive_data:
                raise RecoveryError("Read-only inspection cannot be combined with staging")
            if args.diagnose_symlinks:
                print(json.dumps(diagnose_symlinks(args.recovery_set), indent=2, sort_keys=True))
            else:
                _, counts = verify_set(args.recovery_set, metadata_only=True)
                print(json.dumps({
                    "mode": "metadata-only",
                    "manifest_sha256_and_size": "pass",
                    "member_paths_types_and_limits": "pass",
                    "symlink_targets_validated_for_extraction": False,
                    "safe_to_stage": False,
                    "entries": counts["entries"],
                    "regular_files": counts["regular_files"],
                    "symlinks": counts["symlinks"],
                    "directories": counts["directories"],
                }, sort_keys=True, indent=2))
            return 0
        if bool(args.stage_dir) != args.acknowledge_sensitive_data:
            raise RecoveryError("--stage-dir and --acknowledge-sensitive-data must be used together")
        records, counts = verify_set(args.recovery_set)
        print("Manifest SHA-256: PASS")
        print("Archive structure: PASS")
        for name in ("entries", "regular_files", "symlinks", "directories", "expanded_bytes", *PATH_GROUPS):
            print(f"{name}: {counts[name]}")
        if args.stage_dir:
            stage(args.recovery_set, args.stage_dir, records)
            print("Private staging: PASS (no production files changed)")
            print("Sensitive staged data must be protected and cleaned up by the operator.")
        return 0
    except (RecoveryError, OSError, ValueError, json.JSONDecodeError,
            tarfile.TarError, EOFError) as error:
        # Avoid dumping sensitive paths or exception contents to logs.
        print(f"Recovery validation FAILED ({type(error).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
