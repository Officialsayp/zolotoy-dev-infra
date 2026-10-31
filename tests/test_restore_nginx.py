"""Synthetic-only tests for guarded Nginx restoration. No VPS or S3 access."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import restore_nginx as nginx


class NginxRestoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nginx-stage-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / "stage"
        self.newhost = self.root / "newhost"
        for base in (self.stage, self.newhost):
            (base / "etc/nginx/conf.d").mkdir(parents=True)
        self.backups = self.root / "backups"
        self.backups.mkdir()
        self.files = {
            "etc/nginx/nginx.conf": b"events {}\n",
            "etc/nginx/conf.d/site.conf": b"server { listen 8000; }\n",
        }
        for name, data in self.files.items():
            (self.stage / name).write_bytes(data)
        self.plan = self.root / "review.json"
        self.write_plan()

    def write_plan(self, rows=None):
        if rows is None:
            rows = [{"path": name, "sha256": hashlib.sha256(data).hexdigest()}
                    for name, data in self.files.items()]
        self.plan.write_text(json.dumps({"schema": 1, "files": rows}))

    def apply(self, validator):
        return nginx.apply_reviewed(
            self.stage, self.plan, self.newhost, self.backups, validator
        )

    def test_inventory_and_sha_review(self):
        self.assertEqual(len(nginx.inventory(self.stage)), 2)
        self.assertEqual(len(nginx.load_plan(self.stage, self.plan)), 2)

    def test_success_saves_restricted_journal_without_reload(self):
        old = self.newhost / "etc/nginx/nginx.conf"
        old.write_bytes(b"old config\n")
        old.chmod(0o640)
        check = []
        journal = self.apply(lambda: check.append("nginx -t") or True)
        self.assertEqual(check, ["nginx -t"])
        self.assertEqual(old.read_bytes(), self.files["etc/nginx/nginx.conf"])
        self.assertEqual((journal / "old-000.bin").read_bytes(), b"old config\n")
        self.assertTrue((journal / "journal.json").is_file())
        self.assertEqual(stat.S_IMODE(journal.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((journal / "old-000.bin").stat().st_mode), 0o600)

    def test_syntax_failure_rolls_back_old_and_removes_new(self):
        old = self.newhost / "etc/nginx/nginx.conf"
        old.write_bytes(b"original")
        old.chmod(0o640)
        with self.assertRaises(nginx.RestoreError):
            self.apply(lambda: False)
        self.assertEqual(old.read_bytes(), b"original")
        self.assertEqual(stat.S_IMODE(old.stat().st_mode), 0o640)
        self.assertFalse((self.newhost / "etc/nginx/conf.d/site.conf").exists())

    def test_dangling_live_current_link_blocks_apply(self):
        pointer = self.newhost / "var/www/maxzolotoy/current"
        pointer.parent.mkdir(parents=True)
        pointer.symlink_to("missing")
        with self.assertRaises(nginx.RestoreError):
            self.apply(lambda: True)

    def test_source_symlink_rejected(self):
        src = self.stage / "etc/nginx/conf.d/site.conf"
        src.unlink()
        src.symlink_to("../nginx.conf")
        with self.assertRaises(nginx.RestoreError):
            nginx.load_plan(self.stage, self.plan)

    def test_destination_symlink_rejected(self):
        target = self.newhost / "etc/nginx/nginx.conf"
        target.symlink_to("/etc/passwd")
        with self.assertRaises(nginx.RestoreError):
            self.apply(lambda: True)

    def test_digest_mismatch_rejected(self):
        (self.stage / "etc/nginx/nginx.conf").write_text("changed")
        with self.assertRaises(nginx.RestoreError):
            nginx.load_plan(self.stage, self.plan)

    def test_unsafe_paths_rejected(self):
        paths = (
            "/etc/nginx/nginx.conf",
            "etc/nginx/../ssh/sshd_config",
            "etc/nginx/../../passwd",
            "etc/nginx/private.key",
            "etc/nginx/certificate.pem",
            "etc/nginx/.hidden",
            "etc/systemd/system/evil.service",
        )
        for name in paths:
            with self.subTest(path=name), self.assertRaises(nginx.RestoreError):
                nginx.safe_rel(name)

    def test_repeated_review_path_rejected(self):
        row = {"path": "etc/nginx/nginx.conf",
               "sha256": hashlib.sha256(self.files["etc/nginx/nginx.conf"]).hexdigest()}
        self.write_plan([row, row])
        with self.assertRaises(nginx.RestoreError):
            nginx.load_plan(self.stage, self.plan)

    def test_missing_destination_parent_rejected(self):
        (self.newhost / "etc/nginx/conf.d").rmdir()
        with self.assertRaises(nginx.RestoreError):
            self.apply(lambda: True)

    def test_explicit_rollback_restores_originals(self):
        old = self.newhost / "etc/nginx/nginx.conf"
        old.write_bytes(b"old")
        old.chmod(0o640)
        journal = self.apply(lambda: True)
        nginx.rollback_reviewed(journal, self.newhost, lambda: True)
        self.assertEqual(old.read_bytes(), b"old")
        self.assertEqual(stat.S_IMODE(old.stat().st_mode), 0o640)
        self.assertFalse((self.newhost / "etc/nginx/conf.d/site.conf").exists())

    def test_rollback_refuses_file_changed_since_apply(self):
        journal = self.apply(lambda: True)
        target = self.newhost / "etc/nginx/nginx.conf"
        target.write_bytes(b"edited after deployment")
        with self.assertRaises(nginx.RestoreError):
            nginx.rollback_reviewed(journal, self.newhost, lambda: True)
        self.assertEqual(target.read_bytes(), b"edited after deployment")

    def test_failed_rollback_validation_reapplies_candidate(self):
        (self.newhost / "etc/nginx/nginx.conf").write_bytes(b"old")
        journal = self.apply(lambda: True)
        with self.assertRaises(nginx.RestoreError):
            nginx.rollback_reviewed(journal, self.newhost, lambda: False)
        self.assertEqual((self.newhost / "etc/nginx/nginx.conf").read_bytes(),
                         self.files["etc/nginx/nginx.conf"])
        self.assertTrue((self.newhost / "etc/nginx/conf.d/site.conf").is_file())

    def test_rollback_refuses_live_host(self):
        journal = self.apply(lambda: True)
        pointer = self.newhost / "var/www/zolotoy-dev-production/current"
        pointer.parent.mkdir(parents=True)
        pointer.symlink_to("releases/prod")
        with self.assertRaises(nginx.RestoreError):
            nginx.rollback_reviewed(journal, self.newhost, lambda: True)


if __name__ == "__main__":
    unittest.main()
