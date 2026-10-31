"""Synthetic-only tests: never access the production VPS or real backup credentials."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import review_backup_wrappers as wrappers
from recovery_archive import RecoveryError


def fixtures():
    return {
        "usr/local/sbin/maxzolotoy-offsite-backup": (
            b"#!/bin/sh\nset -eu\n/usr/local/sbin/site-recovery.py offsite\n"
            b"# NEVER-SHOW-THIS-SECRET\n", 0o750, 0, 0,
        ),
        "usr/local/sbin/maxzolotoy-restic-check": (
            b"#!/bin/bash\nset -e\nsource /root/.config/restic/maxzolotoy.env\n"
            b"restic check --read-data\n", 0o750, 0, 0,
        ),
        "usr/local/sbin/site-recovery.py": (
            b"#!/usr/bin/env python3\n# redacted synthetic\n"
            b"import subprocess\nRESTIC_REPOSITORY = 'SENSITIVE-FAKE-REPO'\n"
            b"RESTIC_PASSWORD_FILE = 'SENSITIVE-FAKE-PASSWORD'\n"
            b"def rotate():\n    pass\n", 0o750, 0, 0,
        ),
    }


def make_recovery(base: Path, files=None, links=None):
    archive_dir = base / "sample"
    archive_dir.mkdir()
    archive_path = archive_dir / "recovery.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for name, (body, mode, uid, gid) in (
            fixtures() if files is None else files
        ).items():
            member = tarfile.TarInfo(name)
            member.size = len(body)
            member.mode = mode
            member.uid = uid
            member.gid = gid
            archive.addfile(member, io.BytesIO(body))
        for name, target in (links or {}).items():
            member = tarfile.TarInfo(name)
            member.type = tarfile.SYMTYPE
            member.linkname = target
            archive.addfile(member)
    (archive_dir / "manifest.json").write_text(json.dumps({
        "schema": 1,
        "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "bytes": archive_path.stat().st_size,
    }))
    return archive_dir


class BackupWrapperReviewTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="wrapper-static-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_bounded_source_metadata_succeeds(self):
        report = wrappers.review(make_recovery(self.root))
        self.assertEqual(report["archive_sha256_and_structure"], "pass-metadata-only")
        self.assertTrue(report["wrapper_file_metadata_checks_pass"])
        self.assertFalse(report["safe_to_run_or_restore_without_manual_review"])
        self.assertFalse(report["separate_off_host_s3_and_restic_credentials_verified"])
        self.assertFalse(report["wrapper_behavior_or_runtime_verified"])
        self.assertFalse(report["restic_credential_env_file_in_archive"])
        self.assertEqual(set(report["wrappers"]), set(wrappers.SCRIPTS))
        self.assertEqual(report["wrappers"]["site_recovery"]["interpreter"], "python3")

    def test_classification_does_not_reveal_raw_source_or_secrets(self):
        report = wrappers.review(make_recovery(self.root))
        serialized = json.dumps(report)
        for value in (
            "NEVER-SHOW-THIS-SECRET", "SENSITIVE-FAKE-REPO",
            "SENSITIVE-FAKE-PASSWORD", "source /root/.config",
            "restic check --read-data",
        ):
            self.assertNotIn(value, serialized)
        self.assertTrue(report["wrappers"]["restic_check"]["lexical_indicators"]["mentions_restic"])

    def test_absolute_external_systemd_symlink_does_not_block_readonly_audit(self):
        directory = make_recovery(
            self.root,
            links={"etc/systemd/system/timers.target.wants/restic-check.timer":
                   "/usr/lib/systemd/system/something.timer"}
        )
        report = wrappers.review(directory)
        self.assertTrue(report["wrapper_file_metadata_checks_pass"])
        self.assertFalse(report["archive_symlinks_validated_for_extraction"])

    def test_missing_script_fails_inventory_without_guessing(self):
        files = fixtures()
        files.pop("usr/local/sbin/maxzolotoy-restic-check")
        report = wrappers.review(make_recovery(self.root, files))
        self.assertFalse(report["wrapper_file_metadata_checks_pass"])
        self.assertFalse(report["wrappers"]["restic_check"]["archived_regular_file"])
        self.assertEqual(report["wrappers"]["restic_check"]["interpreter"], "unreadable-or-empty")

    def test_unsafe_mode_and_owner_are_detected(self):
        files = fixtures()
        path = "usr/local/sbin/maxzolotoy-offsite-backup"
        body, _, _, _ = files[path]
        files[path] = (body, 0o777, 1000, 1000)
        report = wrappers.review(make_recovery(self.root, files))
        item = report["wrappers"]["offsite_backup"]
        self.assertFalse(item["root_owned"])
        self.assertFalse(item["not_group_or_world_writable"])
        self.assertFalse(report["wrapper_file_metadata_checks_pass"])

    def test_oversize_source_is_not_read_or_reported(self):
        files = fixtures()
        path = "usr/local/sbin/site-recovery.py"
        files[path] = (b"SECRET-WITHHELD\n" * 30000, 0o750, 0, 0)
        report = wrappers.review(make_recovery(self.root, files))
        self.assertFalse(report["wrappers"]["site_recovery"]["bounded_utf8_source_readable"])
        self.assertFalse(report["wrapper_file_metadata_checks_pass"])
        self.assertNotIn("SECRET-WITHHELD", json.dumps(report))

    def test_comment_only_indicator_is_not_treated_as_execution(self):
        indicators = wrappers.lexical_indicators(
            "# restic forget --prune\n#!/bin/sh\nprintf 'hello'\n"
        )
        self.assertFalse(indicators["mentions_restic"])
        self.assertFalse(indicators["mentions_removal_or_prune"])

    def test_modified_manifest_hash_refused(self):
        directory = make_recovery(self.root)
        file = directory / "manifest.json"
        payload = json.loads(file.read_text())
        payload["sha256"] = "0" * 64
        file.write_text(json.dumps(payload))
        with self.assertRaises(RecoveryError):
            wrappers.review(directory)

    def test_traversal_archive_member_is_refused(self):
        files = fixtures()
        files["../../../escape"] = (b"bad", 0o600, 0, 0)
        with self.assertRaises(RecoveryError):
            wrappers.review(make_recovery(self.root, files))

    def test_root_env_in_archive_is_only_reported_as_boolean(self):
        files = fixtures()
        files[wrappers.CREDENTIAL_ENV_ARCHIVE_PATH] = (
            b"RESTIC_PASSWORD=FAKE-SECRET-DO-NOT-LOG\n", 0o600, 0, 0
        )
        report = wrappers.review(make_recovery(self.root, files))
        self.assertTrue(report["restic_credential_env_file_in_archive"])
        self.assertNotIn("FAKE-SECRET-DO-NOT-LOG", json.dumps(report))
        self.assertFalse(report["separate_off_host_s3_and_restic_credentials_verified"])


if __name__ == "__main__":
    unittest.main()
