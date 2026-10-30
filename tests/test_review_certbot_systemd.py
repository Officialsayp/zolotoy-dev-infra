"""Synthetic-only Certbot/systemd recovery inspection; no real secrets or services."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import review_certbot_systemd as review


def fixtures() -> tuple[dict[str, tuple[bytes, int, int]], dict[str, str]]:
    files: dict[str, tuple[bytes, int, int]] = {}
    links: dict[str, str] = {}
    for name in review.CERT_NAMES:
        files[f"etc/letsencrypt/renewal/{name}.conf"] = (
            (f"[renewalparams]\nauthenticator = webroot\n"
             "webroot_path = /var/lib/letsencrypt\n"
             "private_key = NEVER-LOG-THIS-SECRET\n").encode(), 0o600, 0
        )
        for pem in ("fullchain", "privkey"):
            files[f"etc/letsencrypt/archive/{name}/{pem}1.pem"] = (
                b"SYNTHETIC-NOT-REAL-CERTIFICATE\n", 0o600, 0
            )
            links[f"etc/letsencrypt/live/{name}/{pem}.pem"] = (
                f"../../archive/{name}/{pem}1.pem"
            )
    files[review.HOOK] = (
        b"#!/bin/sh\nset -eu\nif systemctl is-active --quiet nginx; then\n"
        b"    /usr/sbin/nginx -t\n    /usr/bin/systemctl reload nginx\nfi\n",
        0o750, 0
    )
    for base, script in review.BACKUP_SERVICES.items():
        # Synthetic guess for test fixture ONLY; unknown real ExecStart remains
        # unresolved in the audit, irrespective of this placeholder string.
        sample_exec = f"/{script}" if script else "/usr/local/sbin/site-recovery.py check"
        files[f"etc/systemd/system/{base}.service"] = (
            (f"[Unit]\nDescription=Example\n[Service]\n"
             f"Type=oneshot\nExecStart={sample_exec}\n").encode(),
            0o644, 0
        )
        files[f"etc/systemd/system/{base}.timer"] = (
            (f"[Unit]\nDescription=Timer\n[Timer]\n"
             f"OnCalendar=daily\nUnit={base}.service\n").encode(),
            0o644, 0
        )
        if script is not None:
            files[script] = (b"#!/bin/sh\nexit 0\n", 0o750, 0)
    return files, links


def make_set(base: Path, files=None, links=None) -> Path:
    directory = base / "set"
    directory.mkdir(exist_ok=True)
    if files is None or links is None:
        default_files, default_links = fixtures()
        files = default_files if files is None else files
        links = default_links if links is None else links
    with tarfile.open(directory / "recovery.tar.gz", "w:gz") as tar:
        for name, (content, mode, uid) in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            member.mode = mode
            member.uid = uid
            member.gid = 0
            tar.addfile(member, io.BytesIO(content))
        for name, target in links.items():
            member = tarfile.TarInfo(name)
            member.type = tarfile.SYMTYPE
            member.linkname = target
            member.uid = 0
            member.gid = 0
            tar.addfile(member)
    archive = directory / "recovery.tar.gz"
    (directory / "manifest.json").write_text(json.dumps({
        "schema": 1,
        "bytes": archive.stat().st_size,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }))
    (directory / "systemd-unit-states.txt").write_text("synthetic unit listing\n")
    (directory / "packages.tsv").write_text("synthetic packages\n")
    return directory


class ReviewCertbotSystemdTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="safe-host-review-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def run_review(self, files=None, links=None):
        return review.review(make_set(self.root, files=files, links=links))

    def test_all_synthetic_components_present_and_valid(self):
        result = self.run_review()
        self.assertTrue(result["known_scope_checks_pass"])
        self.assertFalse(result["static_review_complete"])
        self.assertEqual(
            result["systemd"]["execstart_manual_review_needed_for"],
            ["maxzolotoy-restic-check"],
        )
        self.assertIsNone(result["systemd"]["backup_units"][1]["service_references_expected_script"])
        self.assertFalse(result["safe_to_apply_without_further_review"])
        self.assertEqual(len(result["certbot"]["renewal_profiles"]), 5)
        self.assertTrue(all(row["live_privkey_present"] for row in result["certbot"]["certificate_paths"]))
        self.assertEqual(len(result["systemd"]["backup_units"]), 2)

    def test_no_private_values_reach_report(self):
        serialized = json.dumps(self.run_review())
        self.assertNotIn("NEVER-LOG-THIS-SECRET", serialized)
        self.assertNotIn("SYNTHETIC-NOT-REAL-CERTIFICATE", serialized)
        self.assertNotIn("ExecStart=", serialized)

    def test_realistic_systemd_absolute_links_are_metadata_only(self):
        files, links = fixtures()
        links["etc/systemd/system/timers.target.wants/certbot.timer"] = (
            "/lib/systemd/system/certbot.timer"
        )
        report = self.run_review(files, links)
        self.assertTrue(report["known_scope_checks_pass"])
        self.assertEqual(
            report["recovery_archive_hash_and_structure"], "pass-metadata-only"
        )
        self.assertFalse(report["symlink_targets_extraction_safe"])
        self.assertFalse(report["safe_to_apply_without_further_review"])

    def test_failures_only_keeps_unknown_exec_out_of_failed_checks(self):
        result = review.summarize(self.run_review())
        self.assertEqual(result["failed_known_checks"], [])
        self.assertEqual(
            result["unresolved_manual_reviews"],
            ["systemd.execstart.maxzolotoy-restic-check"],
        )
        self.assertFalse(result["static_review_complete"])

    def test_failures_only_reports_mismatched_webroot_and_hook(self):
        files, links = fixtures()
        name = "etc/letsencrypt/renewal/zolotoy.dev.conf"
        data, mode, uid = files[name]
        files[name] = (data.replace(b"/var/lib/letsencrypt", b"/tmp/wrong"), mode, uid)
        hook, hook_mode, hook_uid = files[review.HOOK]
        files[review.HOOK] = (hook.replace(b"set -eu\\n", b""), hook_mode, hook_uid)
        report = review.summarize(self.run_review(files, links))
        self.assertIn(
            "certbot.renewal_profiles.zolotoy.dev.expected_webroot",
            report["failed_known_checks"],
        )
        self.assertIn(
            "certbot.deploy_hook.strict_failure_handling",
            report["failed_known_checks"],
        )
        self.assertNotIn("NEVER-LOG-THIS-SECRET", json.dumps(report))

    def test_missing_renewal_profile_marks_review_incomplete(self):
        files, links = fixtures()
        files.pop("etc/letsencrypt/renewal/zolotoy.dev.conf")
        result = self.run_review(files, links)
        self.assertFalse(result["static_review_complete"])
        self.assertFalse(result["certbot"]["renewal_profiles"][3]["present"])

    def test_wrong_renewal_webroot_marks_review_incomplete(self):
        files, links = fixtures()
        name = "etc/letsencrypt/renewal/maxzolotoy.com.conf"
        data, mode, uid = files[name]
        files[name] = (data.replace(b"/var/lib/letsencrypt", b"/tmp/acme"), mode, uid)
        result = self.run_review(files, links)
        self.assertFalse(result["certbot"]["renewal_profiles"][0]["expected_webroot"])

    def test_renewer_using_non_webroot_is_not_accepted(self):
        files, links = fixtures()
        name = "etc/letsencrypt/renewal/maxzolotoy.com.conf"
        data, mode, uid = files[name]
        files[name] = (data.replace(b"authenticator = webroot", b"authenticator = standalone"), mode, uid)
        self.assertFalse(self.run_review(files, links)["static_review_complete"])

    def test_missing_hook_is_reported(self):
        files, links = fixtures()
        files.pop(review.HOOK)
        result = self.run_review(files, links)
        self.assertFalse(result["certbot"]["deploy_hook"]["present"])
        self.assertFalse(result["static_review_complete"])

    def test_hook_requires_executable_bit(self):
        files, links = fixtures()
        data, _, uid = files[review.HOOK]
        files[review.HOOK] = (data, 0o640, uid)
        self.assertFalse(self.run_review(files, links)["certbot"]["deploy_hook"]["archived_executable_bit"])

    def test_hook_requires_safe_owner_mode(self):
        files, links = fixtures()
        data, mode, _ = files[review.HOOK]
        files[review.HOOK] = (data, mode, 1000)
        self.assertFalse(self.run_review(files, links)["certbot"]["deploy_hook"]["root_owned_and_not_group_world_writable"])

    def test_invalid_posix_shell_is_reported(self):
        files, links = fixtures()
        data, mode, uid = files[review.HOOK]
        files[review.HOOK] = (data + b"if then\n", mode, uid)
        self.assertFalse(self.run_review(files, links)["certbot"]["deploy_hook"]["posix_syntax_pass"])

    def test_extra_hook_command_prevents_positive_known_scope(self):
        files, links = fixtures()
        content, mode, uid = files[review.HOOK]
        files[review.HOOK] = (
            content.replace(b"fi\n", b"fi\n/usr/bin/curl https://example.invalid/\n"),
            mode, uid
        )
        report = self.run_review(files, links)
        self.assertTrue(report["certbot"]["deploy_hook"]["posix_syntax_pass"])
        self.assertFalse(report["certbot"]["deploy_hook"]["only_expected_hook_commands"])
        self.assertFalse(report["known_scope_checks_pass"])

    def test_missing_set_eu_prevents_positive_known_scope(self):
        files, links = fixtures()
        content, mode, uid = files[review.HOOK]
        files[review.HOOK] = (content.replace(b"set -eu\n", b""), mode, uid)
        report = self.run_review(files, links)
        self.assertFalse(report["certbot"]["deploy_hook"]["strict_failure_handling"])
        self.assertFalse(report["known_scope_checks_pass"])

    def test_restic_check_exec_is_never_assumed_verified(self):
        report = self.run_review()
        check_service = report["systemd"]["backup_units"][1]
        self.assertTrue(check_service["execstart_present"])
        self.assertTrue(check_service["execstart_requires_manual_review"])
        self.assertIsNone(check_service["script_regular_file"])
        self.assertIsNone(check_service["service_references_expected_script"])

    def test_missing_backup_timer_marks_review_incomplete(self):
        files, links = fixtures()
        files.pop("etc/systemd/system/maxzolotoy-restic-check.timer")
        result = self.run_review(files, links)
        self.assertFalse(result["static_review_complete"])
        self.assertFalse(result["systemd"]["backup_units"][1]["timer_regular_file"])

    def test_wrong_service_exec_is_reported(self):
        files, links = fixtures()
        name = "etc/systemd/system/maxzolotoy-offsite-backup.service"
        data, mode, uid = files[name]
        files[name] = (data.replace(b"/usr/local/sbin/maxzolotoy-offsite-backup", b"/bin/false"), mode, uid)
        self.assertFalse(self.run_review(files, links)["systemd"]["backup_units"][0]["service_references_expected_script"])

    def test_missing_local_script_marks_review_incomplete(self):
        files, links = fixtures()
        files.pop(review.BACKUP_SERVICES["maxzolotoy-offsite-backup"])
        self.assertFalse(self.run_review(files, links)["static_review_complete"])

    def test_missing_unit_schedule_is_reported(self):
        files, links = fixtures()
        name = "etc/systemd/system/maxzolotoy-restic-check.timer"
        files[name] = (b"[Timer]\nAccuracySec=1h\n", 0o644, 0)
        self.assertFalse(self.run_review(files, links)["systemd"]["backup_units"][1]["has_timer_schedule"])

    def test_changed_archive_digest_is_refused(self):
        directory = make_set(self.root)
        manifest = directory / "manifest.json"
        data = json.loads(manifest.read_text())
        data["sha256"] = "0" * 64
        manifest.write_text(json.dumps(data))
        with self.assertRaises(Exception):
            review.review(directory)

    def test_tar_symlink_certificate_paths_are_checked_as_present(self):
        result = self.run_review()
        self.assertTrue(all(p["live_fullchain_present"] and p["live_privkey_present"]
                            for p in result["certbot"]["certificate_paths"]))

    def test_trailing_suspect_section_does_not_override_allowlisted_values(self):
        config = (
            "[renewalparams]\nauthenticator = webroot\nwebroot_path = /var/lib/letsencrypt\n"
            "[other]\nauthenticator = malicious\n"
        )
        values = review.section_values(config, "renewalparams", ("authenticator", "webroot_path"))
        self.assertEqual(values["authenticator"], "webroot")

    def test_duplicate_conflicting_renewal_option_invalidates_profile(self):
        config = "[renewalparams]\nauthenticator = webroot\nauthenticator = standalone\n"
        self.assertEqual(review.section_values(config, "renewalparams", ("authenticator",)), {})


if __name__ == "__main__":
    unittest.main()
