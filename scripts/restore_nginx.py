#!/usr/bin/env python3
"""Inventory and conditionally install REVIEWED Nginx files on a NEW VPS.

Default is read-only. Apply requires root, hostname confirmation, and exact
approved SHA256 values. It never handles TLS keys, systemd, DNS, site releases,
reloads, or operations against the source Recovery Set.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Callable

LIMIT_FILES = 80
LIMIT_FILE_BYTES = 2 * 1024 * 1024
LIMIT_TOTAL_BYTES = 16 * 1024 * 1024
PRIVATE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".p8", ".pkcs12")
SITE_LINKS = (
    "var/www/maxzolotoy/current",
    "var/www/zolotoy-dev-production/current",
    "var/www/zolotoy-dev/releases/current",
)


class RestoreError(Exception):
    """Refused to modify an unsafe or unreviewed host."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_rel(raw: str) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise RestoreError("Malformed source path")
    if raw.startswith("/") or ".." in PurePosixPath(raw).parts:
        raise RestoreError("Absolute or traversal paths forbidden")
    parts = PurePosixPath(raw).parts
    if len(parts) < 3 or parts[:2] != ("etc", "nginx"):
        raise RestoreError("Only reviewed Nginx config files are supported")
    if PurePosixPath(raw).as_posix() != raw or "." in parts:
        raise RestoreError("Noncanonical path")
    if raw.endswith(PRIVATE_SUFFIXES) or any(p.startswith(".") for p in parts[2:]):
        raise RestoreError("Private/key/hidden files excluded")
    return raw


def safe_file(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT_FILE_BYTES:
        raise RestoreError("Source must be a small regular file")


def normal_parent_path(base: Path, rel: str) -> Path:
    path = base
    for part in PurePosixPath(rel).parts[:-1]:
        path /= part
        try:
            info = path.lstat()
        except FileNotFoundError as exc:
            raise RestoreError("Missing source/destination parent") from exc
        if not stat.S_ISDIR(info.st_mode):
            raise RestoreError("Symlinked or unsafe source/destination parent")
    return path / PurePosixPath(rel).name


def load_plan(stage: Path, plan_file: Path) -> list[tuple[str, Path, str]]:
    if not stage.is_absolute() or stage.is_symlink() or not stage.is_dir():
        raise RestoreError("Stage must be a real absolute directory")
    if plan_file.is_symlink() or not plan_file.is_file() or plan_file.stat().st_size > 512 * 1024:
        raise RestoreError("Missing or unsafe review plan")
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    if not isinstance(plan, dict) or plan.get("schema") != 1 or not isinstance(plan.get("files"), list):
        raise RestoreError("Invalid review plan schema")
    rows = plan["files"]
    if not 0 < len(rows) <= LIMIT_FILES:
        raise RestoreError("Review plan must contain 1..80 explicit files")
    records = []
    seen = set()
    total = 0
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            raise RestoreError("Review plan contains unexpected fields")
        rel = safe_rel(row["path"])
        expected = row["sha256"]
        if rel in seen or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise RestoreError("Duplicate plan file or invalid checksum")
        seen.add(rel)
        source = normal_parent_path(stage, rel)
        safe_file(source)
        total += source.stat().st_size
        if total > LIMIT_TOTAL_BYTES:
            raise RestoreError("Review plan exceeds size limit")
        if sha256(source) != expected:
            raise RestoreError("Source differs from approved SHA-256")
        records.append((rel, source, expected))
    return records


def inventory(stage: Path) -> list[dict]:
    if not stage.is_absolute() or stage.is_symlink() or not stage.is_dir():
        raise RestoreError("Stage must be a real absolute directory")
    tree = stage / "etc/nginx"
    if tree.is_symlink() or not tree.is_dir():
        raise RestoreError("Nginx configuration tree absent")
    candidates = []
    for path in sorted(tree.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(stage).as_posix()
        try:
            safe_rel(rel)
            safe_file(normal_parent_path(stage, rel))
        except (RestoreError, OSError):
            continue
        candidates.append({"path": rel, "sha256": sha256(path)})
    return candidates


def assert_new_host(root: Path) -> None:
    for name in SITE_LINKS:
        path = root.joinpath(*PurePosixPath(name).parts)
        if path.is_symlink() or path.exists():
            raise RestoreError("Existing site current pointer: potential live host")


def atomic_write(destination: Path, data: bytes, mode: int) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=".reviewed-nginx-", dir=destination.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        tmp.chmod(mode)
        os.replace(tmp, destination)
    finally:
        if tmp.exists():
            tmp.unlink()


def apply_reviewed(
    stage: Path,
    plan_file: Path,
    root: Path,
    backup_parent: Path,
    validator: Callable[[], bool],
) -> Path:
    """Apply only to a new host. CLI fixes root to '/' and checks UID and hostname."""
    assert_new_host(root)
    files = load_plan(stage, plan_file)
    snapshots = []
    for rel, _, _ in files:
        dest = normal_parent_path(root, rel)
        if dest.is_symlink():
            raise RestoreError("Destination symlink refused")
        if dest.exists():
            if not stat.S_ISREG(dest.lstat().st_mode):
                raise RestoreError("Destination is not a regular file")
            previous, previous_mode = dest.read_bytes(), stat.S_IMODE(dest.stat().st_mode)
        else:
            previous, previous_mode = None, None
        snapshots.append((dest, previous, previous_mode))
    if backup_parent.is_symlink() or not backup_parent.is_dir():
        raise RestoreError("Protected backup parent is missing")
    journal_dir = Path(tempfile.mkdtemp(prefix="nginx-review-", dir=backup_parent))
    journal_dir.chmod(0o700)
    records = []
    try:
        for index, (dest, previous, mode) in enumerate(snapshots):
            if previous is not None:
                old = journal_dir / f"old-{index:03d}.bin"
                with old.open("xb") as output:
                    output.write(previous)
                old.chmod(0o600)
            records.append({
                "path": files[index][0],
                "prior": previous is not None,
                "prior_mode": mode,
                "sha256_prior": hashlib.sha256(previous).hexdigest() if previous is not None else None,
                "sha256_applied": files[index][2],
                "backup_name": f"old-{index:03d}.bin" if previous is not None else None,
            })
        manifest = journal_dir / "journal.json"
        with manifest.open("x", encoding="utf-8") as output:
            json.dump({"schema": 1, "files": records}, output, indent=2)
        manifest.chmod(0o600)
        for (_, src, expected), (dest, _, _) in zip(files, snapshots):
            if sha256(src) != expected:
                raise RestoreError("Stage changed after preflight")
            atomic_write(dest, src.read_bytes(), 0o644)
        if not validator():
            raise RestoreError("Nginx syntax validation failed; rollback initiated")
        return journal_dir
    except BaseException:
        for dest, previous, mode in reversed(snapshots):
            if previous is None:
                if dest.exists() and not dest.is_symlink():
                    dest.unlink()
            else:
                atomic_write(dest, previous, mode)
        raise


def rollback_reviewed(
    journal_directory: Path, root: Path, validator: Callable[[], bool]
) -> None:
    """Explicit rollback before any site cutover; refuse unexpected file edits."""
    assert_new_host(root)
    if journal_directory.is_symlink() or not journal_directory.is_dir():
        raise RestoreError("Unsafe rollback journal")
    if stat.S_IMODE(journal_directory.stat().st_mode) & 0o077:
        raise RestoreError("Rollback journal permissions too permissive")
    manifest = journal_directory / "journal.json"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 512 * 1024:
        raise RestoreError("Missing or invalid rollback metadata")
    info = json.loads(manifest.read_text(encoding="utf-8"))
    rows = info.get("files") if isinstance(info, dict) and info.get("schema") == 1 else None
    if not isinstance(rows, list) or not 0 < len(rows) <= LIMIT_FILES:
        raise RestoreError("Invalid rollback manifest")
    targets = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "path", "prior", "prior_mode", "sha256_prior", "sha256_applied", "backup_name"
        }:
            raise RestoreError("Invalid rollback record")
        rel = safe_rel(row["path"])
        if rel in seen:
            raise RestoreError("Duplicate rollback destination")
        seen.add(rel)
        dest = normal_parent_path(root, rel)
        if dest.is_symlink() or not dest.is_file() or sha256(dest) != row["sha256_applied"]:
            raise RestoreError("Installed file changed: rollback refused")
        current = dest.read_bytes()
        if row["prior"] is True:
            saved_name = f"old-{len(targets):03d}.bin"
            if (row["backup_name"] != saved_name
                    or not isinstance(row["prior_mode"], int)
                    or not 0 <= row["prior_mode"] <= 0o777):
                raise RestoreError("Invalid old file reference")
            old = journal_directory / saved_name
            if old.is_symlink() or not old.is_file() or sha256(old) != row["sha256_prior"]:
                raise RestoreError("Prior file backup hash mismatch")
            previous, mode = old.read_bytes(), row["prior_mode"]
        elif row["prior"] is False and row["backup_name"] is None:
            previous, mode = None, None
        else:
            raise RestoreError("Invalid rollback record flags")
        targets.append((dest, previous, mode, current))
    try:
        for dest, previous, mode, _ in targets:
            if previous is None:
                dest.unlink()
            else:
                atomic_write(dest, previous, mode)
        if not validator():
            raise RestoreError("Rolled back config invalid; reapplying candidate")
    except BaseException:
        for dest, _, _, current in targets:
            atomic_write(dest, current, 0o644)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, help="Private staged recovery root")
    parser.add_argument("--plan", type=Path, help="Operator-reviewed JSON, exact SHA-256 list")
    parser.add_argument("--apply", action="store_true", help="New-host guarded configuration install")
    parser.add_argument("--rollback-journal", type=Path, help="Explicit pre-cutover rollback")
    parser.add_argument("--confirm-host", help="Exact hostname, required for any write")
    args = parser.parse_args()
    try:
        if args.apply and args.rollback_journal:
            raise RestoreError("Select only one change operation")
        if not args.apply and not args.rollback_journal:
            if args.stage is None:
                raise RestoreError("Read-only mode requires --stage")
            if args.plan:
                selected = load_plan(args.stage, args.plan)
                print("Reviewed plan valid; files:", len(selected))
            else:
                print(json.dumps({"schema": 1, "files": inventory(args.stage)}, indent=2))
            return 0
        if os.geteuid() != 0 or args.confirm_host != os.uname().nodename:
            raise RestoreError("Write requires root and an exact hostname confirmation")
        root = Path("/")
        assert_new_host(root)

        def validate() -> bool:
            result = subprocess.run(["/usr/sbin/nginx", "-t"],
                                    capture_output=True, timeout=20)
            return result.returncode == 0

        private_root = Path("/var/backups/site-recovery")
        if (private_root.is_symlink() or not private_root.is_dir()
                or stat.S_IMODE(private_root.stat().st_mode) & 0o077):
            raise RestoreError("Root-only backup/lock directory must be mode 0700")
        lock = private_root / ".reviewed-nginx.lock"
        fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a+") as handle:
            lock_stat = os.fstat(handle.fileno())
            if (not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != 0
                    or stat.S_IMODE(lock_stat.st_mode) & 0o077):
                raise RestoreError("Unsafe recovery lock file")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RestoreError("Another Nginx recovery operation is in progress") from exc
            if args.rollback_journal:
                rollback_reviewed(args.rollback_journal, root, validate)
                print("Reviewed rollback: PASS; NO Nginx reload")
            else:
                if args.stage is None or args.plan is None:
                    raise RestoreError("Apply requires --stage and --plan")
                saved = apply_reviewed(
                    args.stage, args.plan, root, Path("/var/backups/site-recovery"),
                    validate
                )
                print("Reviewed Nginx files installed; nginx -t PASS; NO reload")
                print("Protected rollback journal:", saved)
        return 0
    except (RestoreError, OSError, ValueError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as exc:
        print(f"Nginx recovery refused/failed ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
