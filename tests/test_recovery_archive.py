"""Offline synthetic tests for the guarded recovery archive inspector.

No production credentials, actual site backups, network access or VPS needed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import recovery_archive as recovery


FILES = {
    "etc/nginx/nginx.conf": b"events {}\n",
    "etc/letsencrypt/archive/example.com/cert1.pem": b"synthetic-public-certificate\n",
    "var/www/maxzolotoy/releases/rel1/index.html": b"<html>synthetic</html>\n",
}
LINKS = {
    "etc/letsencrypt/live/example.com/cert.pem": "../../archive/example.com/cert1.pem",
    "var/www/maxzolotoy/current": "releases/rel1",
}


def make_set(base: Path, *, files=None, links=None, special=None) -> Path:
    source = base / "set"
    source.mkdir(exist_ok=True)
    with tarfile.open(source / "recovery.tar.gz", "w:gz") as archive:
        for name, data in (FILES if files is None else files).items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(data))
        for name, destination in (LINKS if links is None else links).items():
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = destination
            archive.addfile(info)
        if special:
            info = tarfile.TarInfo(special[0])
            info.type = special[1]
            info.linkname = special[2]
            archive.addfile(info)
    payload = source / "recovery.tar.gz"
    manifest = {
        "schema": 1,
        "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
        "bytes": payload.stat().st_size,
    }
    (source / "manifest.json").write_text(json.dumps(manifest))
    return source


class RecoveryArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="recovery-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_valid_manifest_and_safe_links(self):
        source = make_set(self.root)
        entries, counts = recovery.verify_set(source)
        self.assertEqual(counts["regular_files"], 3)
        self.assertEqual(counts["symlinks"], 2)
        self.assertEqual(counts["nginx"], 1)
        self.assertEqual(counts["zolotoy_staging"], 0)
        self.assertEqual(len(entries), 5)

    def test_stage_creates_private_files_and_relative_links(self):
        source = make_set(self.root)
        entries, _ = recovery.verify_set(source)
        dest = self.root / "restored"
        recovery.stage(source, dest, entries)
        self.assertEqual(
            (dest / "var/www/maxzolotoy/releases/rel1/index.html").read_bytes(),
            FILES["var/www/maxzolotoy/releases/rel1/index.html"],
        )
        self.assertTrue((dest / "var/www/maxzolotoy/current").is_symlink())
        self.assertEqual(os.readlink(dest / "var/www/maxzolotoy/current"), "releases/rel1")
        self.assertTrue((dest / "etc/letsencrypt/live/example.com/cert.pem").is_symlink())
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o700)
        self.assertEqual(
            stat.S_IMODE((dest / "etc/nginx/nginx.conf").stat().st_mode), 0o600
        )

    def test_wrong_sha_rejected(self):
        source = make_set(self.root)
        manifest_path = source / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(recovery.RecoveryError):
            recovery.verify_set(source)

    def test_absolute_path_rejected(self):
        source = make_set(self.root, files={"/etc/cron.d/evil": b"x"}, links={})
        with self.assertRaises(recovery.RecoveryError):
            recovery.verify_set(source)

    def test_parent_traversal_rejected(self):
        source = make_set(self.root, files={"../../escape": b"x"}, links={})
        with self.assertRaises(recovery.RecoveryError):
            recovery.verify_set(source)

    def test_absolute_symlink_rejected(self):
        source = make_set(self.root, files=FILES, links={"var/www/other": "/etc/passwd"})
        with self.assertRaises(recovery.RecoveryError):
            recovery.verify_set(source)

    def test_symlink_escape_rejected(self):
        source = make_set(self.root, files=FILES, links={"var/www/other": "../../../etc/passwd"})
        with self.assertRaises(recovery.RecoveryError):
            recovery.verify_set(source)

    def test_nested_file_under_symlink_rejected(self):
        source = make_set(
            self.root,
            files={"etc/nginx/host.conf": b"x", "var/www/site/sneaky.txt": b"bad"},
            links={"var/www/site": "../nginx"},
        )
        with self.assertRaises(recovery.RecoveryError):
            recovery.verify_set(source)

    def test_missing_link_target_rejected(self):
        source = make_set(self.root, files=FILES, links={"var/www/site/current": "missing"})
        with self.assertRaises(recovery.RecoveryError):
            recovery.verify_set(source)

    def test_hardlink_rejected(self):
        source = make_set(self.root, special=("var/www/hard", tarfile.LNKTYPE, "etc/nginx/nginx.conf"))
        with self.assertRaises(recovery.RecoveryError):
            recovery.verify_set(source)

    def test_existing_stage_target_rejected(self):
        target = self.root / "already-exists"
        target.mkdir()
        with self.assertRaises(recovery.RecoveryError):
            recovery.validate_stage_target(target)

    def test_stage_target_outside_tmp_rejected(self):
        with self.assertRaises(recovery.RecoveryError):
            recovery.validate_stage_target(Path("/etc/never-create-this-recovery-dir"))

    def test_manifest_must_be_regular_file(self):
        source = make_set(self.root)
        (source / "manifest.json").unlink()
        (source / "manifest.json").symlink_to("recovery.tar.gz")
        with self.assertRaises(recovery.RecoveryError):
            recovery.verify_set(source)


if __name__ == "__main__":
    unittest.main()
