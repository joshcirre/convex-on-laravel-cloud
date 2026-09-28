# Self-hosting Convex on Laravel Cloud

Run the open-source Convex backend on [Laravel Cloud](https://cloud.laravel.com), with managed Postgres and private object storage.

This starter follows the flow of Convex's [self-hosting guide](https://github.com/get-convex/convex-backend/blob/main/self-hosted/README.md) and [Fly.io deployment guide](https://github.com/get-convex/convex-backend/blob/main/self-hosted/advanced/fly/README.md). Its backend scripts come from the working [Lawn deployment](https://github.com/joshcirre/lawn/tree/main/convex-backend).

This repository deploys one Convex backend application. Your frontend lives in its own project and connects to the backend's public URL. You can run the upstream dashboard locally against that backend.

**Validation:** Lawn's backend was verified on Laravel Cloud with release `precompiled-2026-09-26-27ef234` and `convex@1.41.0`. This starter pins that release and retains its Cloud networking workarounds. This standalone repository is ready for its first Cloud deployment test.

## Setup

Fork [joshcirre/convex-on-laravel-cloud](https://github.com/joshcirre/convex-on-laravel-cloud), or connect that repository directly to Laravel Cloud.

You need a Laravel Cloud account, a Convex application, and Node.js/npm locally to deploy its functions. Docker is optional, only for the local dashboard below.

```text
package.json + package-lock.json  Node runtime detection and build/start commands
build.sh                         Downloads the pinned Convex backend binary
start.sh                         Configures storage and starts the backend and proxy
proxy.mjs                        Handles Cloud's IPv6 ingress and WebSocket headers
```

Cloud uses its [Node.js runtime](https://laravel.com/cloud/docs/runtimes). The build downloads a precompiled Rust binary; Node is also needed for Convex's `"use node"` actions. Keep `package-lock.json` so Cloud detects the runtime correctly.

## Deploying the backend

There are two separate deployments: first start the Convex service on Cloud, then push your application's Convex functions to it.

### 1. Create the Cloud application

Create an application from your repository and configure its environment:

| Setting | Value |
| --- | --- |
| Root directory | `/` (repository root) |
| Runtime | Node.js 22 |
| Build command | `npm run build` |
| Start command | `npm start` |
| Compute | Start with 2 GB RAM (`flex-2gb` in Lawn's configuration) |
| Replicas | One; disable autoscaling or set minimum and maximum to 1 |
| Scale-to-zero / hibernation | Disabled |
| Region | Same region as your Postgres database |

Save the public HTTPS URL Cloud assigns. The examples below use `https://YOUR-BACKEND.laravel.cloud`; replace it with your actual URL. Do not include a trailing slash.

Keep the backend always on: it owns a database lease and maintains subscriptions and scheduled work. Multiple replicas sharing the same instance are not a supported scaling strategy for this starter. See [Cloud compute settings](https://laravel.com/cloud/docs/compute).

### 2. Attach Postgres and a private bucket

Choose an instance name, such as `convex`. Create a managed Postgres cluster and a database named **`convex`**, then attach that database to the backend environment.

The database name must match `INSTANCE_NAME`, replacing hyphens with underscores. For example, `my-convex` requires `my_convex`. If Cloud initially creates a database named `production`, create and attach the correctly named database instead.

Attach a private object-storage bucket to the same backend environment with read/write credentials. This stores deployed function modules, uploaded files, search indexes, and import/export objects. The starter maps the attached bucket to all five Convex storage settings.

The scripts accept Cloud's injected variables:

| Resource | Accepted variables |
| --- | --- |
| Postgres | `DATABASE_URL`, or `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`, and `DB_CONNECTION=pgsql` |
| Bucket credentials | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| Bucket name | `AWS_BUCKET` |
| Bucket endpoint | `AWS_ENDPOINT_URL` or `AWS_ENDPOINT` |
| Bucket region | `AWS_REGION` or `AWS_DEFAULT_REGION`; defaults to `auto` |

**Both resources are required.** The starter refuses to boot without database and bucket configuration. Cloud's local filesystem is temporary; it cannot safely hold SQLite, deployed functions, or uploaded files between deployments.

For external resources, see Convex's [SQL configuration](https://github.com/get-convex/convex-backend/blob/main/self-hosted/advanced/postgres_or_mysql.md) and [S3 configuration](https://github.com/get-convex/convex-backend/blob/main/self-hosted/advanced/s3_storage.md). Advanced `POSTGRES_URL`/`MYSQL_URL` overrides must be server URLs without a database path or query parameters; they bypass the script's attached-database name check and hostname rewrite.

### 3. Configure the backend environment

Generate an instance secret locally:

```sh
openssl rand -hex 32
```

Store it in a password manager and Cloud's environment variables. Generate it once per instance and keep it stable across deployments.

```dotenv
INSTANCE_NAME=convex
INSTANCE_SECRET=YOUR_GENERATED_64_CHARACTER_HEX_SECRET
CONVEX_CLOUD_ORIGIN=https://YOUR-BACKEND.laravel.cloud
CONVEX_BACKEND_VERSION=precompiled-2026-09-26-27ef234
```

`CONVEX_SITE_ORIGIN` defaults to `https://YOUR-BACKEND.laravel.cloud/http`. Leave it unset for this setup. Cloud supplies `PORT`; leave it alone.

The `.env.example` file is a reference template. The scripts read environment variables, not dotenv files. Enter the values in Cloud before deploying.

### 4. Deploy and check the backend

Deploy from the Cloud dashboard. The build downloads the Linux binary for the build machine's architecture and checks that it runs.

Look for these startup values in the logs:

```text
db=postgres-v5
storage=--s3-storage
proxy: [::]:3000 -> 127.0.0.1:3010
```

The ports vary with Cloud's `PORT`. Confirm the public backend responds:

```sh
curl --fail https://YOUR-BACKEND.laravel.cloud/version
```

Expect HTTP 200 and a backend version. This checks availability; the function and dashboard checks below exercise the deployment further.

### 5. Generate an admin key

In the backend environment's Cloud **Commands** tab, run:

```sh
./bin/convex-local-backend keygen admin-key \
  --instance-name "$INSTANCE_NAME" \
  --instance-secret "$INSTANCE_SECRET"
```

Run from the application root. Save the output securely. The command uses the deployed binary and configured instance identity, so you do not need a local binary or Docker.

The key grants administrative access to this backend and is used by both the CLI and dashboard. It is not a frontend API key. Cloud command output may be visible to other operators with access to the environment.

### 6. Deploy your Convex functions

In **your application project**, create an ignored `.env.self-hosted` file:

```dotenv
CONVEX_SELF_HOSTED_URL=https://YOUR-BACKEND.laravel.cloud
CONVEX_SELF_HOSTED_ADMIN_KEY=YOUR_ADMIN_KEY
```

Add `.env.self-hosted` to that project's `.gitignore`. Use a Convex CLI compatible with your backend; Lawn verified version `1.41.0` with the pinned release.

```sh
# For a new project; existing projects should keep their tested dependency version.
npm install convex@1.41.0

npx convex deploy --env-file .env.self-hosted
```

Set any environment variables your functions require before deploying them:

```sh
# Example; replace with a variable your application actually needs.
npx convex env set AUTH_ISSUER_URL https://auth.example.com --env-file .env.self-hosted
```

These are **Convex function environment variables**, separate from Cloud's backend-process variables. Modules that read configuration during import may fail deployment until those variables exist.

For development against a separate instance:

```sh
npx convex dev --env-file .env.self-hosted
```

That command continuously pushes changes. Give development and production separate backends, databases, buckets, and instance identities.

### HTTP actions

A function registered at `/sendEmail` is reachable at:

```text
https://YOUR-BACKEND.laravel.cloud/http/sendEmail
```

Use the backend origin without `/http` for Convex clients and the CLI. Use the `/http` base for HTTP actions, webhooks, and applicable auth callbacks. Inside functions, Convex supplies `CONVEX_CLOUD_URL` and `CONVEX_SITE_URL` from the origins configured above.

## Running the dashboard

Run the upstream dashboard locally and connect it to your Cloud backend:

```sh
docker run --rm -p 127.0.0.1:6791:6791 \
  -e NEXT_PUBLIC_DEPLOYMENT_URL=https://YOUR-BACKEND.laravel.cloud \
  ghcr.io/get-convex/convex-dashboard:latest
```

Open `http://localhost:6791` and enter the admin key generated above. The browser connects directly to your public backend. For repeatable Docker deployments, choose and pin a compatible image tag or digest instead of `latest`.

## Deploying your frontend app

Host your frontend on Cloud or another provider. Set the public backend URL using the variable your framework reads, for example:

```dotenv
# Vite
VITE_CONVEX_URL=https://YOUR-BACKEND.laravel.cloud

# Next.js
NEXT_PUBLIC_CONVEX_URL=https://YOUR-BACKEND.laravel.cloud
```

Only the URL belongs in client-visible variables. If CI deploys functions, give that build process `CONVEX_SELF_HOSTED_URL` and `CONVEX_SELF_HOSTED_ADMIN_KEY` as secrets. Do not pass the admin key into your frontend bundle. See the [upstream frontend guidance](https://github.com/get-convex/convex-backend/blob/main/self-hosted/README.md#deploying-your-frontend-app).

## Verify the complete setup

- `/version` returns HTTP 200.
- `convex deploy` completes against the intended self-hosted URL.
- Dashboard login succeeds and shows the deployed functions.
- A query subscription updates after a mutation; the browser's network panel shows a successful WebSocket connection.
- A known HTTP action responds at `/http/YOUR_ROUTE` using its expected method.
- Data, uploaded files, and deployed functions remain available after a backend redeploy.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Cloud detects JavaScript instead of Rust | Expected. Keep Node 22 and the included lockfile; the Rust binary is downloaded during build. |
| Missing instance name or secret | Set both in the backend environment before deployment. |
| Attached database name mismatch | Use the `INSTANCE_NAME` database, with hyphens replaced by underscores. |
| Database or bucket required error | Attach both resources and verify the injected variable names against the table above. |
| Postgres TLS hostname error | The script handles Lawn's observed Cloud-to-Neon hostname pattern for `DATABASE_URL`/`DB_*`. For a different pattern, verify the provider's actual TLS hostname; do not disable TLS verification. |
| Healthy backend logs but Cloud reports unhealthy | Keep `proxy.mjs` and `start.sh` together. The proxy listens on IPv6 and forwards to the IPv4 backend. |
| WebSocket 400: Connection header did not include upgrade | The supplied proxy restores upgrade headers affected by Cloud's ingress. Cloud's Reverb/Pusher WebSockets resource is not needed. |
| Repeated Lease Lost errors | Check for duplicate replicas, overlapping manual deployments, or another environment using the same database identity. |
| Disk exhaustion during build or startup | Increase backend compute; the binary and temporary files need local space even with remote storage. |
| Function push fails reading an environment variable | Set the variable with `convex env set` before pushing functions. |
| Dashboard rejects the key | Check the backend URL and generate a key using that backend's instance name and secret. |

## Backups and upgrades

Keep the backend release pin explicit. Before upgrading, export your data using the CLI, preserve function environment variables securely, and verify your database and bucket backup/recovery arrangements. Include uploaded files in your backup plan; a database-only backup is insufficient.

Follow Convex's [upgrade instructions](https://github.com/get-convex/convex-backend/blob/main/self-hosted/advanced/upgrading.md), then test the new release against a separate instance before updating production. Changing a version pin and redeploying can run database migrations; do not assume an older binary can undo them.

The backend scripts retain Lawn's IPv6 and WebSocket workarounds. Recheck them when Cloud's ingress or Convex changes. This starter is a community deployment recipe, not a managed Convex service.
