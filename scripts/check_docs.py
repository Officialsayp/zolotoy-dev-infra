#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    'README.md', 'AGENTS.md', 'inventory/services.yaml',
    'docs/architecture.md', 'docs/environments.md', 'docs/deployment-plan.md',
    'docs/security.md', 'docs/observability.md', 'docs/backups.md',
    'docs/runbooks/bootstrap-selectel.md', 'docs/runbooks/deploy.md',
    'docs/runbooks/rollback.md', 'docs/runbooks/portable-vps-migration.md',
    'docs/runbooks/web-vps-bootstrap.md', 'inventory/web-vps-observed-packages.yaml',
    'iac/web-baseline.yml', 'iac/requirements.txt',
    'scripts/recovery_archive.py', 'tests/test_recovery_archive.py',
    'docs/runbooks/recovery-archive-staging.md',
    'docs/runbooks/nginx-reviewed-restore.md', 'scripts/restore_nginx.py',
    'tests/test_restore_nginx.py',
    'scripts/review_certbot_systemd.py', 'tests/test_review_certbot_systemd.py',
    'docs/runbooks/certbot-systemd-recovery.md',
    'docs/adr/README.md',
]
LINK_RE = re.compile(r'(?<!!)\[[^\]]+\]\(([^)]+)\)')
SECRET_NAMES = {'.env', 'id_rsa', 'id_ed25519', 'terraform.tfvars'}

def fail(message: str) -> None:
    print(f'ERROR: {message}', file=sys.stderr)
    raise SystemExit(1)

for rel in REQUIRED:
    if not (ROOT / rel).is_file():
        fail(f'missing required file: {rel}')

errors = []
for md in ROOT.rglob('*.md'):
    text = md.read_text(encoding='utf-8')
    if not text.endswith('\n'):
        errors.append(f'{md.relative_to(ROOT)}: missing final newline')
    for target in LINK_RE.findall(text):
        target = target.strip()
        if not target or target.startswith(('#', 'http://', 'https://', 'mailto:')):
            continue
        path_part = target.split('#', 1)[0].split('?', 1)[0]
        if not path_part:
            continue
        resolved = (md.parent / path_part).resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError:
            errors.append(f'{md.relative_to(ROOT)}: link escapes repo: {target}')
            continue
        if not resolved.exists():
            errors.append(f'{md.relative_to(ROOT)}: broken relative link: {target}')

for p in ROOT.rglob('*'):
    if p.is_file() and p.name in SECRET_NAMES:
        errors.append(f'forbidden secret-like file committed: {p.relative_to(ROOT)}')

inventory = (ROOT / 'inventory/services.yaml').read_text(encoding='utf-8')
for forbidden_status in ['deployed: true', 'deployment_status: deployed']:
    if forbidden_status in inventory:
        errors.append('bootstrap inventory must not claim backend production is deployed')

if errors:
    for error in errors:
        print(f'ERROR: {error}', file=sys.stderr)
    raise SystemExit(1)

print('Infrastructure repository checks passed.')
