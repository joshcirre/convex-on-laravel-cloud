# Keep the demo inexpensive

Start with **only the Convex backend, private MySQL, and one private bucket on Cloud**. Run the demo frontend on your computer and use the [local dashboard](../README.md#running-the-dashboard-locally-instead). Hosting the frontend and dashboard is optional; each adds compute cost.

## Two profiles

| Setting | Low-cost demo | Continuous service |
| --- | --- | --- |
| Backend | One 1 GB instance | One 1 GB or larger instance, sized from measurements |
| Backend sleep | Five-minute hibernation; accepts cold starts and paused work | Disabled |
| MySQL | Smallest eligible private size, 5 GB storage; five-minute suspend | Sized for workload; disable suspend if uninterrupted operation is required |
| Dashboard/frontend | Local by default; hosted only when requested | As required |
| Hosted dashboard/frontend | 512 MB each, five-minute hibernation | Size and sleep according to usage |
| Backups | Test data only; no automatic backups assumed | Configure and test recovery |

The September 28, 2026 test passed on a **1 GB backend**, **512 MB hosted dashboard**, and **512 MB hosted frontend** with MySQL and S3 storage. A 512 MB backend has not been validated. Those results used legacy compute IDs; newly available cheaper CPU families still need their own workload checks.

Sleeping is appropriate for a disposable demo that accepts interruptions. It is not a substitute for always-on execution of scheduled Convex work. Existing subscriptions may disconnect or keep the service awake. MySQL sleeps only after it has no connections during its idle timeout, so Convex's connection pool may prevent database sleep. This last point is an inference from [MySQL's sleep behavior](https://laravel.com/cloud/docs/resources/databases/laravel-mysql#scale-to-zero), not a measured result for this deployment.

Close frontend/dashboard tabs and development watchers, then test an idle interval, wake-up latency, reconnection, and a new mutation before claiming the deployment reliably sleeps and resumes. Monitor actual billed usage. Do not add an external health-check cron that continuously wakes a demo you intend to sleep.

## Choose size IDs, not just RAM

Before provisioning, check current [Cloud pricing](https://laravel.com/cloud/docs/pricing), region availability, and `cloud instance:sizes --json -n` (discover its help first). The live CLI listed both modern and legacy sizes during the audit. Identical RAM does not mean identical price or CPU allocation.

Ohio example, checked September 28, 2026:

| Resource | Size ID | Monthly compute/storage amount if continuously awake |
| --- | --- | ---: |
| Backend, 1 GB | `flex.m-1vcpu-1gb` | $7.00 |
| Optional dashboard, 512 MB | `flex.g-1vcpu-512mb` | $5.00 |
| Optional frontend, 512 MB | `flex.g-1vcpu-512mb` | $5.00 |
| MySQL, size actually returned by the test deployment | `mysql-flex-512mb` | $6.60 |
| MySQL storage | 5 GB | $0.50 |
| **Backend + database/storage only** | | **$14.10** |
| **All three hosted applications + database/storage** | | **$24.10** |

These are estimates using the official size-specific pricing table, not a promised bill or a hard spending cap. Bucket storage/requests, backups, bandwidth overages, taxes, and other usage are additional. Rates vary by region. Starter's $5 organization fee includes $5 usage credit; if fully available to this deployment, those offset at these usage levels. Existing organizations share their plan/credit across applications; do not charge or credit it twice in estimates.

The current test deployment uses legacy `flex-1gb` ($12) and two `flex-512mb` ($6 each), so its corresponding estimate is **$31.10**. These resources were not resized during this documentation audit. Changing the size family needs its own deployment/performance verification.

The pricing table also lists `db-flex.m-1vcpu-512mb` at $5.50, which would reduce these estimates by another $1.10 if provisionable. The test's cluster returned `mysql-flex-512mb`; availability or migration to the cheaper database family has **not** been verified. Read back the actual cluster configuration rather than assuming the CLI preset's requested ID was retained.

## Avoid unnecessary setup and cost

- Reuse existing Cloud CLI credentials and GitHub integration. A logged-out Cloud browser is not a reason to reauthenticate.
- Use the existing public repositories unless the user wants changes. Forking and another repository are optional.
- Ask for missing choices once. “Cheapest demo” plus a clear estimate is a useful budget preference; do not require an invented monthly ceiling.
- Keep the frontend/dashboard local until someone asks to host them. The optional hosted apps do not need their own databases or buckets.
- Use one backend replica, with no autoscaling. Multiple replicas sharing this instance identity are not this starter's scaling model.
- Keep build, backend deployment, function deployment, and frontend deployment separate. Do not repeatedly rebuild all three apps to fix one setting.
- Report what remains billable after stopping compute, including database and object storage. Removing persistent resources requires a deliberate cleanup decision and can destroy data.

Use the [agent runbook](agents/README.md) for the terminal setup and API bridge. Account creation, billing, and new OAuth/GitHub permissions still require the user's involvement.
