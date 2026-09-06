# Backup and restore plan

No `zolotoy.dev` backend production data exists at bootstrap time. This document defines the minimum
requirements before calling a later deployment recoverable.

## Required backup classes

1. service-owned PostgreSQL databases;
2. infrastructure configuration needed to rebuild the environment;
3. selected persistent state that cannot be reconstructed from the database/event source;
4. secret material via a separate secure secret-management/recovery process (never inside Git backups).

Redis cache for URL Shortener is reconstructable and should not be treated as the primary durable copy.
Kafka retention is not a replacement for database backup.

## First practical baseline

For a single-VPS portfolio environment, a reasonable first implementation is:

- scheduled `pg_dump`/custom-format backups per owned database;
- encrypted off-host backup storage (Selectel S3 is a candidate);
- retention documented explicitly;
- periodic restore into a disposable environment;
- restore result recorded, not assumed.

The existing `saypix` project uses encrypted restic backups to Selectel S3. Reusing the operational
pattern is reasonable, but backend database dumps need database-aware creation/verification before
restic uploads them.

## Pre-deploy rule

A migration that can make rollback unsafe requires a backup/restore assessment before production
deployment. Do not promise automatic rollback across incompatible database migrations.
