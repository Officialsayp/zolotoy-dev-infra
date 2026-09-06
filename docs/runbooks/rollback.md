# Runbook — rollback backend deployment

Status: process skeleton until active production manifests exist.

## Rollback unit

Rollback is based on the **previous immutable image/config set**, not `latest`.

## Procedure

1. stop further deployment attempts;
2. identify whether failure is application-only, edge config, dependency, or data/schema related;
3. if schema is backward-compatible, restore previous image references and redeploy;
4. verify readiness and representative external requests;
5. if a migration is incompatible with the previous binary, do not blindly roll back the image — follow
   the database recovery plan for that migration;
6. document the failure and the actual recovery result.

## Data safety

Never use `docker compose down -v`, delete named volumes, wipe databases or prune production storage as
part of a routine rollback. Those are destructive actions requiring separate explicit authorization.
