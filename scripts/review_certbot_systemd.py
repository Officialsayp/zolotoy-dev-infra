#!/usr/bin/env python3
"""Read-only TLS/systemd recovery inventory from an already verified Recovery Set.

Does not print file contents, private keys, renewal parameters or ExecStart values.
Does not extract, install, enable, reload, contact ACME or change any services.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

from recovery_archive import RecoveryError, verify_set

CERT_NAMES = (
    "maxzolotoy.com",
    "www.maxzolotoy.com",
    "origin.maxzolotoy.com",
    "zolotoy.dev",
    "origin.zolotoy.dev",
)
HOOK = "etc/letsencrypt/renewal-hooks/deploy/20-nginx-reload"
# Only the offsite wrapper ExecStart is established by owner-provided evidence.
# The Restic-check ExecStart was NOT provided: never invent its script path.
BACKUP_SERVICES = {
    "maxzolotoy-offsite-backup": "usr/local/sbin/maxzolotoy-offsite-backup",
    "maxzolotoy-restic-check": None,
}
CONFIG_LIMIT = 128 * 1024


def limited_text(archive: tarfile.TarFile, item: tarfile.TarInfo) -> str | None:
    """Read selected config files only; never echo bytes or exception details."""
    if not item.isfile() or item.size < 0 or item.size > CONFIG_LIMIT:
        return None
    source = archive.extractfile(item)
    if source is None:
        return None
    with source:
        data = source.read(CONFIG_LIMIT + 1)
    if len(data) > CONFIG_LIMIT or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def section_values(text: str, section: str, allowed_keys: tuple[str, ...]) -> dict[str, str]:
    """Parse only allowlisted INI scalars and ignore all other (possibly secret) keys."""
    current = ""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#") or line.startswith(";"):
            continue
        match = re.fullmatch(r"\[([^\]]+)\]", line)
        if match:
            current = match.group(1).strip()
            continue
        if current != section or "=" not in line:
            continue
        key, value = (v.strip() for v in line.split("=", 1))
        if key in allowed_keys:
            if key in result and result[key] != value:
                return {}
            result[key] = value
    return result


def owner_and_mode(member: tarfile.TarInfo) -> bool:
    return member.uid == 0 and member.gid == 0 and (member.mode & 0o022) == 0


def static_hook_checks(text: str | None) -> dict[str, bool]:
    if text is None:
        return {
            "posix_syntax_pass": False,
            "nginx_active_guard": False,
            "nginx_config_check": False,
            "nginx_reload_command": False,
            "strict_failure_handling": False,
            "only_expected_hook_commands": False,
        }
    try:
        check = subprocess.run(
            ["/bin/sh", "-n"],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=5,
            check=False,
        )
        syntactically_valid = check.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        syntactically_valid = False
    expected_commands = (
        "#!/bin/sh",
        "set -eu",
        "if systemctl is-active --quiet nginx; then",
        "/usr/sbin/nginx -t",
        "/usr/bin/systemctl reload nginx",
        "fi",
    )
    actual_commands = tuple(line.strip() for line in text.splitlines() if line.strip())
    return {
        "posix_syntax_pass": syntactically_valid and text.startswith("#!/bin/sh\n"),
        "strict_failure_handling": "set -eu" in actual_commands,
        # Prevent a syntactically valid but modified hook from falsely passing.
        "only_expected_hook_commands": actual_commands == expected_commands,
        "nginx_active_guard": bool(
            re.search(r"(?m)^\s*if\s+systemctl\s+is-active\s+--quiet\s+nginx\s*;\s*then\s*$", text)
        ),
        "nginx_config_check": bool(
            re.search(r"(?m)^\s*/usr/sbin/nginx\s+-t\s*$", text)
        ),
        "nginx_reload_command": bool(
            re.search(r"(?m)^\s*/usr/bin/systemctl\s+reload\s+nginx\s*$", text)
        ),
    }


def review(recovery_set: Path) -> dict[str, Any]:
    # This independently checks archive SHA256 and rejects unsafe archive members
    # before reading any selected metadata or config.
    # Read-only: absolute/dangling links are audited as metadata only.
    # Do not use these records for extraction. The strict staging guard remains.
    records, _ = verify_set(recovery_set, metadata_only=True)
    members = {name: member for member, name in records}
    result: dict[str, Any] = {
        "schema": 1,
        "mode": "offline-read-only",
        "recovery_archive_hash_and_structure": "pass-metadata-only",
        "symlink_targets_extraction_safe": False,
        "certbot": {"renewal_profiles": [], "deploy_hook": {}, "certificate_paths": []},
        "systemd": {"backup_units": [], "package_units": "reinstall-and-verify-on-new-host"},
        "unverified": [
            "absolute-and-external-archived-symlink-targets",
            "original-vps-loss-independent-restic-credentials",
            "actual-unattended-acme-renewal",
            "restored-private-key-trust-and-permissions",
            "systemd-unit-install-enable-and-runtime",
            "live-dns-https-and-deployment",
        ],
    }
    with tarfile.open(recovery_set / "recovery.tar.gz", "r:gz") as archive:
        profiles: list[dict[str, Any]] = []
        cert_paths: list[dict[str, Any]] = []
        for name in CERT_NAMES:
            conf = members.get(f"etc/letsencrypt/renewal/{name}.conf")
            options = section_values(
                limited_text(archive, conf), "renewalparams", ("authenticator", "webroot_path")
            ) if conf and conf.isfile() and conf.size <= CONFIG_LIMIT else {}
            profiles.append({
                "name": name,
                "present": bool(conf and conf.isfile()),
                "webroot_authenticator": options.get("authenticator") == "webroot",
                "expected_webroot": options.get("webroot_path") == "/var/lib/letsencrypt",
            })
            fullchain = members.get(f"etc/letsencrypt/live/{name}/fullchain.pem")
            privkey = members.get(f"etc/letsencrypt/live/{name}/privkey.pem")
            cert_paths.append({
                "name": name,
                "live_fullchain_present": bool(fullchain and (fullchain.isfile() or fullchain.issym())),
                "live_privkey_present": bool(privkey and (privkey.isfile() or privkey.issym())),
            })
        result["certbot"]["renewal_profiles"] = profiles
        result["certbot"]["certificate_paths"] = cert_paths

        hook = members.get(HOOK)
        script = limited_text(archive, hook) if hook and hook.isfile() else None
        result["certbot"]["deploy_hook"] = {
            "present": bool(hook and hook.isfile()),
            "root_owned_and_not_group_world_writable": bool(hook and hook.isfile() and owner_and_mode(hook)),
            "archived_executable_bit": bool(hook and hook.isfile() and hook.mode & 0o111),
            **static_hook_checks(script),
        }

        units = []
        for unit, script_path in BACKUP_SERVICES.items():
            service_name = f"etc/systemd/system/{unit}.service"
            timer_name = f"etc/systemd/system/{unit}.timer"
            service = members.get(service_name)
            timer = members.get(timer_name)
            executable = members.get(script_path) if script_path else None
            service_text = limited_text(archive, service) if service and service.isfile() else None
            timer_text = limited_text(archive, timer) if timer and timer.isfile() else None
            svc_settings = section_values(service_text, "Service", ("ExecStart",)) if service_text is not None else {}
            timer_settings = section_values(
                timer_text, "Timer", ("OnCalendar", "OnBootSec", "OnUnitActiveSec")
            ) if timer_text is not None else {}
            units.append({
                "unit": unit,
                "service_regular_file": bool(service and service.isfile()),
                "timer_regular_file": bool(timer and timer.isfile()),
                "service_safe_owner_mode": bool(service and service.isfile() and owner_and_mode(service)),
                "timer_safe_owner_mode": bool(timer and timer.isfile() and owner_and_mode(timer)),
                "execstart_present": bool(svc_settings.get("ExecStart")),
                # Null means source evidence is insufficient, NOT a match.
                "service_references_expected_script": (
                    script_path in svc_settings.get("ExecStart", "") if script_path else None
                ),
                "script_regular_file": (
                    bool(executable and executable.isfile()) if script_path else None
                ),
                "execstart_requires_manual_review": script_path is None,
                "has_timer_schedule": bool(timer_settings),
            })
        result["systemd"]["backup_units"] = units
        result["systemd"]["unit_state_inventory_present"] = (
            (recovery_set / "systemd-unit-states.txt").is_file()
            and not (recovery_set / "systemd-unit-states.txt").is_symlink()
        )
        result["systemd"]["package_inventory_present"] = (
            (recovery_set / "packages.tsv").is_file()
            and not (recovery_set / "packages.tsv").is_symlink()
        )

    profiles_ok = all(
        p["present"] and p["webroot_authenticator"] and p["expected_webroot"]
        for p in profiles
    )
    certificate_paths_ok = all(
        p["live_fullchain_present"] and p["live_privkey_present"]
        for p in cert_paths
    )
    hook_ok = all(result["certbot"]["deploy_hook"].values())
    units_basic_ok = all(
        u["service_regular_file"] and u["timer_regular_file"]
        and u["service_safe_owner_mode"] and u["timer_safe_owner_mode"]
        and u["execstart_present"] and u["has_timer_schedule"]
        for u in units
    )
    known_script_checks_ok = all(
        u["service_references_expected_script"] and u["script_regular_file"]
        for u in units if not u["execstart_requires_manual_review"]
    )
    unresolved_exec = [
        u["unit"] for u in units if u["execstart_requires_manual_review"]
    ]
    result["systemd"]["execstart_manual_review_needed_for"] = unresolved_exec
    result["known_scope_checks_pass"] = bool(
        profiles_ok and certificate_paths_ok and hook_ok
        and units_basic_ok and known_script_checks_ok
        and result["systemd"]["unit_state_inventory_present"]
        and result["systemd"]["package_inventory_present"]
    )
    # The real check service's command remains unknown until owner evidence
    # or separate authorized inspection resolves it.
    result["static_review_complete"] = (
        result["known_scope_checks_pass"] and not unresolved_exec
    )
    result["safe_to_apply_without_further_review"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recovery_set", type=Path)
    args = parser.parse_args()
    try:
        result = review(args.recovery_set)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (RecoveryError, OSError, ValueError, KeyError, tarfile.TarError) as exc:
        # In particular, never print potentially secret source lines or paths
        # from a malformed archive/renewal file.
        print(f"Recovery review refused ({type(exc).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
