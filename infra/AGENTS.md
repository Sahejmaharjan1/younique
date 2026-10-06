# infra/AGENTS.md

Rules for `infra/`. The root `AGENTS.md` applies too. Topology:
`docs/02-system-architecture.md` §6.

## Layout

```
terraform/
├── modules/          reusable: cloud_run_service, cloud_sql, gcs_bucket,
│                     task_queue, pubsub_topic, kms_keyring, alb, monitoring
└── envs/
    ├── shared/       Artifact Registry, Workload Identity Federation, TF state bucket
    ├── dev/          zonal SQL, no HA, min_instances 0
    ├── staging/      prod-shaped, anonymized data
    └── prod/         regional HA, PITR, CMEK, Cloud Armor
```

**Per-environment directories, not Terraform workspaces.** Workspace state collisions are a
recurring and expensive mistake, and a directory makes "what is actually in prod" readable
without knowing which workspace is selected.

An environment directory contains only module calls and values. **Never a bare resource in an
env directory** — if it exists in one environment and not another, that divergence is how
staging stops predicting prod.

## Non-negotiables

1. **No service-account JSON keys.** Anywhere. Ever. CI authenticates by Workload Identity
   Federation. A leaked key is the most common cloud breach vector for OSS projects, and WIF
   removes the artifact entirely.
2. **Least privilege, per service.** Each Cloud Run service has its own service account with
   only the roles it needs. `worker` gets `cloudkms.cryptoKeyDecrypter`; `web` gets nothing.
   Never `roles/editor`, never a shared runtime identity.
3. **Private IP for Cloud SQL.** No public IP, no authorized-networks list. Access via Direct
   VPC egress from Cloud Run.
4. **`/internal/*` is not in the ALB URL map.** Those routes must be unreachable from the
   internet even if an audience check has a bug. Defence in depth.
5. **Uniform bucket-level access on every bucket.** No per-object ACLs, so object permissions
   cannot drift from the application's model.
6. **CMEK on the artifacts bucket and the prod SQL instance.** Keys from our own keyring.
7. **Deletion protection** on prod Cloud SQL and the artifacts bucket. `prevent_destroy` in the
   lifecycle block as a second layer.
8. **Everything is tagged** `env`, `service`, `managed-by=terraform`, `cost-center`. Untagged
   resources are invisible in the cost dashboard, and an untracked cost is an eventual incident.

## Cloud Run

```hcl
module "api" {
  source                = "../../modules/cloud_run_service"
  name                  = "api"
  ingress               = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  min_instances         = 1          # avoid cold start on the user-facing path
  max_instances         = 50         # bounds the DB connection math — see below
  concurrency           = 40
  timeout_seconds       = 3600       # SSE streams and foreground runs
  cpu_idle              = false      # keep CPU during a stream
  service_account_email = google_service_account.api.email
}
```

- `max_instances` is a **required** argument in our module with no default. An unbounded service
  is an unbounded bill and an unbounded number of database connections.
- **Do the connection math before changing `max_instances`.**
  `max_instances × pool_size ≤ Cloud SQL max_connections − headroom`. `api` uses a direct pool
  of 5; the `worker` fleet goes through PgBouncer in transaction mode. Exceeding this browns out
  the entire application, and it is the classic serverless-plus-Postgres failure.
- `worker` and `scanner` are `INGRESS_TRAFFIC_INTERNAL_ONLY`.
- New revisions deploy with `--no-traffic`, are smoke-tested at their tag URL, then take traffic
  in steps.

## Cloud Tasks and Pub/Sub

- Cloud Tasks for **work dispatch** (named tasks give dedup, per-queue concurrency caps,
  scheduled delivery, declarative retry). Pub/Sub for the **event bus** (fan-out). Do not mix
  the roles.
- Every queue sets `max_concurrent_dispatches`, `max_dispatches_per_second`, `max_attempts`, and
  backoff bounds. These are per-queue backpressure, and they are the only thing standing between
  one noisy tenant and everyone else.
- Every Pub/Sub subscription has a **dead-letter topic** and an alert on its depth. A DLQ with
  no alert is a silent data-loss mechanism.
- Exactly **one** Cloud Scheduler job for the minute tick, plus the nightly rollup and retention
  jobs. User schedules are database rows, never GCP resources — see
  `docs/00-assumptions-and-decisions.md` §3.5.

## Secrets

- Secret Manager holds **platform** secrets only: OAuth client secrets, Firebase admin
  credentials, the DB password, Langfuse keys. Mounted as env vars at boot, pinned to a version
  (never `latest`, so a rotation cannot silently change a running revision).
- User secrets (provider keys, connector tokens) are envelope-encrypted in Postgres. Do not add
  Terraform for them.
- The KMS keyring has `prevent_destroy`. Destroying the KEK permanently destroys every user's
  keys and tokens, including in backups.

## CI checks

`terraform fmt -check`, `terraform validate`, `tflint`, and `checkov` on every `infra/` PR.
`terraform plan` is posted as a PR comment; `apply` requires a merge to `main` for `dev` and a
manual approval for `staging` and `prod`.

A plan containing a `destroy` of a stateful resource (SQL instance, bucket, KMS key) fails CI
unless the PR carries the `infra-destructive` label and a maintainer approval.

## Cost guards

- Budget alerts per project at 50 %, 80 %, and 100 % of the monthly forecast.
- `max_instances` on every service, `min_instances = 0` everywhere except `api`.
- GCS lifecycle rules: `uploads-staging` 24 h, `exports` 7 days, artifacts to Nearline at 90
  days.
- Log exclusion filters for health checks and static-asset access logs, which are otherwise a
  surprisingly large share of the Cloud Logging bill.
- Cloud SQL right-sized per environment, with `dev` zonal and stoppable.
