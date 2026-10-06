# Terraform

Modules live in `modules/`. `cloud_run_service` requires `max_instances` and has no default.

Environments are directories, not workspaces: `envs/shared`, `envs/dev`, `envs/staging`, `envs/prod`.

## Cloud SQL connection math

Direct VPC egress from Cloud Run to a private Cloud SQL IP. Budget one server connection per Cloud Run instance times `max_instances`, plus a small pool for migrations. With `max_instances = 20` on the API and a pool of 10, plan for at least 200 connections plus the worker fleet. Set the instance `max_connections` above that sum. PgBouncer transaction mode is for the worker fleet only, because `LISTEN/NOTIFY` and session settings cannot cross it.

## Deploy

The deploy workflow pushes a revision with `--no-traffic`, curls the tagged URL, shifts 10 percent, then 100 percent. Rollback is `update-traffic` back to the `stable` tag and completes without a rebuild.
