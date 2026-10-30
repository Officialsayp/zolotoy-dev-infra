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
        sample_exec = f"/{script}"
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
        self.assertTrue(result["static_review_complete"])
        self.assertEqual(result["systemd"]["execstart_manual_review_needed_for"], [])
        self.assertTrue(result["systemd"]["backup_units"][1]["service_references_expected_script"])
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

    def test_failures_only_reports_confirmed_script_path(self):
        result = review.summarize(self.run_review())
        self.assertEqual(result["failed_known_checks"], [])
        self.assertEqual(result["webroot_evidence_sources"], {
            "webroot_map": 0, "webroot_path": 5, "missing": 0,
        })
        self.assertEqual(result["unresolved_manual_reviews"], [])
        self.assertTrue(result["static_review_complete"])

    def test_failures_only_reports_mismatched_webroot_and_hook(self):
        files, links = fixtures()
        name = "etc/letsencrypt/renewal/zolotoy.dev.conf"
        data, mode, uid = files[name]
        files[name] = (data.replace(b"/var/lib/letsencrypt", b"/tmp/wrong"), mode, uid)
        hook, hook_mode, hook_uid = files[review.HOOK]
        files[review.HOOK] = (hook.replace(b"set -eu\n", b""), hook_mode, hook_uid)
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

    def test_certbot_trailing_comma_webroot_path_is_valid(self):
        files, links = fixtures()
        for name in review.CERT_NAMES:
            path = f"etc/letsencrypt/renewal/{name}.conf"
            payload, mode, uid = files[path]
            files[path] = (
                payload.replace(
                    b"webroot_path = /var/lib/letsencrypt\n",
                    b"webroot_path = /var/lib/letsencrypt,\n",
                ), mode, uid
            )
        report = self.run_review(files, links)
        self.assertTrue(report["known_scope_checks_pass"])
        self.assertEqual(
            {item["webroot_source"] for item in report["certbot"]["renewal_profiles"]},
            {"webroot_path"},
        )

    def test_certbot_nested_webroot_map_without_plain_path_is_valid(self):
        files, links = fixtures()
        for name in review.CERT_NAMES:
            path = f"etc/letsencrypt/renewal/{name}.conf"
            payload, mode, uid = files[path]
            replacement = (
                f"[[webroot_map]]\n{name} = /var/lib/letsencrypt\n"
            ).encode()
            files[path] = (
                payload.replace(b"webroot_path = /var/lib/letsencrypt\n", replacement),
                mode, uid
            )
        report = self.run_review(files, links)
        self.assertTrue(report["known_scope_checks_pass"])
        self.assertEqual(
            {item["webroot_source"] for item in report["certbot"]["renewal_profiles"]},
            {"webroot_map"},
        )

    def test_certbot_domain_map_overrides_plain_root_and_detects_mismatch(self):
        config = (
            "[renewalparams]\nauthenticator = webroot\n"
            "webroot_path = /var/lib/letsencrypt,\n"
            "[[webroot_map]]\nzolotoy.dev = /wrong/root\n"
        )
        source, valid = review.inspect_webroot(config, "zolotoy.dev")
        self.assertEqual(source, "webroot_map")
        self.assertFalse(valid)

    def test_certbot_nested_map_under_unrelated_section_does_not_match(self):
        config = (
            "[renewalparams]\nauthenticator = webroot\n"
            "[acme_renewal_info]\n"
            "[[webroot_map]]\nzolotoy.dev = /var/lib/letsencrypt\n"
        )
        self.assertEqual(
            review.inspect_webroot(config, "zolotoy.dev"),
            ("missing", False),
        )

    def test_certbot_conflicting_duplicate_domain_map_rejected(self):
        config = (
            "[renewalparams]\nauthenticator = webroot\n"
            "[[webroot_map]]\nzolotoy.dev = /var/lib/letsencrypt\n"
            "zolotoy.dev = /different-root\n"
        )
        self.assertEqual(
            review.inspect_webroot(config, "zolotoy.dev"),
            ("webroot_map", False),
        )

    def test_certbot_trailing_comma_does_not_accept_two_paths(self):
        source, valid = review.inspect_webroot(
            "[renewalparams]\nwebroot_path = /var/lib/letsencrypt, /wrong,\n",
            "zolotoy.dev",
        )
        self.assertEqual(source, "webroot_path")
        self.assertFalse(valid)

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

    def test_restic_check_exec_matches_observed_archived_wrapper(self):
        report = self.run_review()
        check_service = report["systemd"]["backup_units"][1]
        self.assertTrue(check_service["execstart_present"])
        self.assertFalse(check_service["execstart_requires_manual_review"])
        self.assertTrue(check_service["script_regular_file"])
        self.assertTrue(check_service["service_references_expected_script"])
        self.assertTrue(check_service["script_root_owned_safe_mode"])
        self.assertTrue(check_service["script_executable"])

    def test_restic_check_exec_rejects_same_name_in_wrong_directory(self):
        files, links = fixtures()
        path = "etc/systemd/system/maxzolotoy-restic-check.service"
        payload, mode, uid = files[path]
        files[path] = (
            payload.replace(
                b"ExecStart=/usr/local/sbin/maxzolotoy-restic-check",
                b"ExecStart=/tmp/maxzolotoy-restic-check"
            ), mode, uid
        )
        report = self.run_review(files, links)
        self.assertFalse(report["known_scope_checks_pass"])
        self.assertFalse(report["systemd"]["backup_units"][1]["service_references_expected_script"])

    def test_restic_check_wrapper_must_be_root_owned_and_executable(self):
        files, links = fixtures()
        path = review.BACKUP_SERVICES["maxzolotoy-restic-check"]
        payload, _, _ = files[path]
        files[path] = (payload, 0o666, 1000)
        report = review.summarize(self.run_review(files, links))
        self.assertFalse(report["known_scope_checks_pass"])
        self.assertIn(
            "systemd.backup_units.maxzolotoy-restic-check.script_executable",
            report["failed_known_checks"],
        )
        self.assertIn(
            "systemd.backup_units.maxzolotoy-restic-check.script_root_owned_safe_mode",
            report["failed_known_checks"],
        )

    def test_restic_check_extra_arguments_require_manual_review(self):
        files, links = fixtures()
        path = "etc/systemd/system/maxzolotoy-restic-check.service"
        payload, mode, uid = files[path]
        files[path] = (
            payload.replace(
                b"ExecStart=/usr/local/sbin/maxzolotoy-restic-check\\n",
                b"ExecStart=/usr/local/sbin/maxzolotoy-restic-check --custom\\n",
            ), mode, uid
        )
        report = self.run_review(files, links)
        unit = report["systemd"]["backup_units"][1]
        self.assertTrue(unit["execstart_requires_manual_review"])
        self.assertTrue(unit["execstart_additional_arguments_present"])
        self.assertFalse(report["static_review_complete"])
        self.assertIn(
            "maxzolotoy-restic-check",
            report["systemd"]["execstart_manual_review_needed_for"],
        )

    def test_matcher_does_not_accept_execstart_embedded_substrings(self):
        matches, extra = review.execstart_binary_matches(
            "/usr/bin/echo /usr/local/sbin/maxzolotoy-restic-check",
            "usr/local/sbin/maxzolotoy-restic-check",
        )
        self.assertFalse(matches)
        self.assertTrue(extra)

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
