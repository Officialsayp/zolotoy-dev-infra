# Runbook — bootstrap Selectel backend host

Status: **planned / not executed for `zolotoy.dev`**.

Use this only after at least one backend service has a real image and readiness contract.

## Preconditions

- selected Selectel project/region/server size;
- SSH key prepared;
- DNS ownership confirmed;
- container registry decision recorded;
- at least one backend image exists;
- service resource requirements measured enough to size the first VPS;
- no production secrets are stored in Git.

Selectel currently provides both standard cloud servers and a Containers Ready image with Docker,
Docker Compose and Portainer preinstalled. Containers Ready documents a minimum of 2 vCPU, 2 GB RAM and
20 GB boot disk; that is a product minimum, not automatically the correct size for Kafka + four services.

## High-level procedure

1. create the VPS with SSH-key access;
2. apply firewall/security-group rules: SSH from intended admin sources, HTTP/HTTPS public, no public DB/
   Redis/Kafka ports;
3. install/verify Docker Engine + Compose (or use the selected prepared image);
4. create a dedicated deployment directory and non-root operational user where practical;
5. authenticate to the selected container registry without committing credentials;
6. install the first validated Compose/Caddy configuration from this repository;
7. validate config before starting;
8. start internal services first, then application, then edge;
9. verify readiness locally on the host;
10. only then publish the service DNS record;
11. verify HTTPS and an external smoke request;
12. record actual server/runtime details in an operations inventory that contains no secret material.

## Do not copy from maxzolotoy.com blindly

The `saypix` runbook is a useful recovery/rollback model, but its IP addresses, domain records, static
release layout and mail-DNS precautions belong to a different site. Reuse process discipline, not
project-specific values.
