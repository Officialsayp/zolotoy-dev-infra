# Web VPS baseline bootstrap — new host only

Status: **reproducible phase-one package/user/directory baseline**, NOT a complete
working-site reconstruction, tested VPS provisioning or provider-specific Terraform.
Created 2026-10-31 after owner-provided Selectel host inspection.

## Evidence and topology

The observed existing VPS runs Ubuntu **26.04.1 LTS** on **x86_64**, with **Nginx** as
its active HTTP(S) server, Certbot for certificate renewal, and Restic for off-site
backups. The required Nginx modules are **njs**, **headers-more**, and **stream**.
Exact observed versions are recorded in
[observed web VPS packages](../../inventory/web-vps-observed-packages.yaml).

The existing Caddy package is **not active** and is deliberately not installed by
this bootstrap. The current VPS has **no Docker**. Go backend Compose, databases
and Kafka are **not deployed here** and are not introduced by this playbook.

## Scope of the Ansible phase-one playbook

The reviewed [web baseline playbook](../../iac/web-baseline.yml) does only:

1. Assert Ubuntu 26.04 x86_64 and require explicit approval outside check mode.
2. Refuse hosts with any existing `current` site pointers (production or staging).
3. Install Ubuntu repository baseline packages: Nginx with njs/headers-more/stream
   modules, Certbot, Restic and operational CLI dependencies.
4. Create password-locked, unprivileged `zolotoydeploy` and `zolotoyprod`
   accounts. The playbook **does not** authorize SSH keys or grant sudo rights.
5. Create the reviewed staging/production release parents and a root-only
   recovery-directory placeholder.

This is an **idempotent partial bootstrap**, not a full immutable-image rebuild.
Package versions intentionally use `state: present`, not exact historical patch
pins: the 2026-10-31 versions are evidence, while a clean Ubuntu mirror can have
newer security updates. Validate Nginx module compatibility on the new host.

Installing Nginx packages can start the distribution's **default** service.
Keep a new VPS isolated from public production DNS, use a restrictive provider
security group, and assume nothing about firewall rules. The playbook does not
activate UFW, issue/reuse TLS certificates, write Nginx configuration, install
systemd recovery jobs, reload services, copy credentials, or change the old host.

The `/var/www/maxzolotoy` site tree is **not recreated by this phase** because
its deploy identity and full ownership have not yet been reviewed. Restore the
correct tree from the verified backup and confirm owner/group identities
**before** enabling deployment workflows. The other two site directories are
empty placeholders only and are not production releases.

## Controller requirements and safe CI verification

Use a trusted operator machine with Python >=3.12 and the pinned
`ansible-core==2.21.5` from [controller requirements](../../iac/requirements.txt).
A Python virtual environment is recommended. Do not run the playbook on the
current Selectel VPS.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r iac/requirements.txt
.venv/bin/ansible-playbook --syntax-check iac/web-baseline.yml
```

Create a **private, uncommitted inventory**, e.g. at
`/secure/path/recovery.ini` (replace `NEW_HOST_IP` and username yourself):

```ini
[web_recovery]
recovery-node ansible_host=NEW_HOST_IP ansible_user=ubuntu
```

Example **read-only** check against that isolated replacement host:

```bash
.venv/bin/ansible-playbook -i /secure/path/recovery.ini \
  --check iac/web-baseline.yml
```

Check mode is **not** a real installation or recovery test. The `apt` module
may require `python3-apt` on a minimal OS image; resolve prerequisites before
an approved apply. The controller requires a verified SSH host key,
trusted sudo access on the new host, and no `StrictHostKeyChecking=no`.

Only on a **new disposable host**, after reviewing a successful check and
confirming the provider's secure console/rollback path, the operator may
explicitly approve applying the playbook:

```bash
.venv/bin/ansible-playbook -i /secure/path/recovery.ini \
  iac/web-baseline.yml -e web_bootstrap_approved=true
```

The playbook's site-pointer guard rejects the existing Selectel production host.
A user could still bypass safeguards by changing the code; do not treat this as
a universal production protection mechanism.

## Required manual and future IaC stages (not performed)

1. Ensure **out-of-band** independent access to Restic password, S3 credentials,
   DNS/provider control and trusted SSH/deployment keys. No secrets in Git.
2. Restore the *reviewed* recovery set to an isolated path and validate its
   manifest/hash, names, permissions and symlink destinations before carefully
   installing required configuration on the new host.
3. Reinstall/verify the actual Nginx routing wrapper and njs files, all active
   site configurations, Certbot renewal settings and executable reload hook;
   run `nginx -t` and hostname-specific HTTPS smoke tests. Ensure `.dev`
   TLS is ready before any DNS cutover.
4. Restore/rebuild both production website releases and preserve atomic
   `current` semantics. Rebuild staging from its separate manually gated
   GitHub Actions workflow after verifying credentials, routes and permissions.
5. Restore systemd recovery jobs, timer schedules, off-site Restic credentials
   and monitoring. Recheck off-host snapshot access **from the new host**.
6. Test real CI/CD to the replacement host, rollback and authorized DNS
   cutover. Until this is rehearsed, **zero downtime and full IaC are unproven**.

For a separately approved, pre-cutover Nginx config installation and rollback,
see [reviewed Nginx restore](nginx-reviewed-restore.md). It does not
restore TLS keys or manage systemd. Verify the relevant backup metadata with
[offline Certbot/systemd review](certbot-systemd-recovery.md) before any
separately authorized activation.

Reference: [portable VPS disaster recovery](portable-vps-migration.md) and
[observed backup/recovery evidence](../backups.md).
