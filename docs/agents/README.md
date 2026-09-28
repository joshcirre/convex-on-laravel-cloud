# Deploy Convex on Laravel Cloud with an agent

Give this guide to an agent with terminal access. It covers onboarding, deploying the backend and optional dashboard, and proving that an application can use them. Read the [backend README](../../README.md) and [dashboard README](../../dashboard/README.md) for the implementation details.

## Copy this prompt

```text
Help me deploy self-hosted Convex on Laravel Cloud using:
https://github.com/joshcirre/convex-on-laravel-cloud/blob/main/docs/agents/README.md

Read that guide and its linked backend/dashboard instructions first. Inspect my
local tools and Cloud access, install missing prerequisites where possible, and
use the Cloud CLI for the steps it supports. Guide me through account creation,
billing, and authorization in the browser. Explain any remaining browser steps.

Use the low-cost demo profile: a 1 GB backend, the smallest private managed
MySQL, private object storage, and five-minute scale-to-zero where supported.
Explain cold starts and sleeping limitations. Run the frontend and dashboard
locally unless I request hosted versions (512 MB each). Discover current size
IDs and prices. Reuse existing authentication and GitHub access. Ask only for
missing organization, region, names, and hosted-app preferences together.
Reuse decisions and authorization I have already supplied. Explain the resources
and their estimated ongoing cost before creating them. A numeric budget is
optional; do not repeatedly ask for one if I already requested the cheapest demo. Do not modify unrelated applications.

Discover the installed CLI's actual flags. Keep secrets out of chat, Git, public
frontend variables, and build logs. Configure persistence before deploying.
Verify the backend, WebSocket connection, function deployment, dashboard login,
and persistence across a redeploy. Report what you tested and anything unfinished.
```

## What can be automated?

**Audited September 28, 2026 against Cloud CLI v0.6.1**, its installed source, a successful independent deployment of this starter, and the [official CLI documentation](https://laravel.com/cloud/docs/api/cli). This is a CLI-first runbook with a small documented API bridge, not a one-command installer. The test deployment used existing CLI credentials and GitHub access without signing into the Cloud website. Recheck help on the installed version; newer releases may close these gaps.

| Step | v0.6.1 route |
| --- | --- |
| Account, plan/payment, organization membership | User in browser |
| Connect GitHub and grant repository access | User in browser; separate from CLI login |
| Install CLI | Composer in terminal |
| Authenticate CLI | `cloud auth -n`, then user authorizes in browser; API token alternative below |
| Create applications/environments, database, bucket | CLI |
| Build/deploy commands, database attachment, variables, compute | CLI; read back settings |
| Node version | Included API helper; no `environment:update` flag |
| Start command | Cloud runs the committed `package.json` start script; verified for all three apps |
| Attach bucket as default filesystem | Included API helper; no CLI attachment flag |
| Configure hibernation | CLI or API helper; read back the effective timeout |
| Deploy, monitor, execute remote commands | CLI |
| Deploy Convex functions | Convex CLI, from the application project |
| Dashboard admin-key login | User in browser |

The [public environment API](https://laravel.com/cloud/docs/api/environments/update-environment) supports `node_version` and `filesystem_keys`, but its documented schema does not expose the custom start command. Do not invent `--start-command`, `--node-version`, or `--filesystem-keys` CLI flags. The helper below uses this documented API with existing CLI credentials. No start-command API override is needed for these repositories because their committed `package.json` scripts provide the correct startup commands. This is an API integration alongside the CLI, not a built-in CLI feature. Preserve existing filesystem attachments when using that API.

## 1. Establish scope and access

Collect only missing decisions: Cloud organization, region, repository/branch, backend and dashboard names, whether a dashboard is wanted, and whether this is a sleeping demo or an always-on service. A budget number is optional when the user already asked for minimum cost. Use a new deployment by default. Do not reuse another project's database, bucket, or instance secret. Record resource IDs and public URLs in a local deployment note without credentials. Discover available regions before offering them; the test requested US West but only Ohio was available as its closest US option. Do not hardcode that observation for future accounts.

Start with the [low-cost profiles](../costs.md): the verified 1 GB backend, smallest private MySQL with 5 GB storage, and a private bucket. Keep the frontend and dashboard local unless hosted versions are requested; each hosted app worked on 512 MB. Use five-minute hibernation for a disposable demo that accepts cold starts and paused work, or disable backend hibernation for continuous scheduled work/subscriptions. Do not claim sleep savings until observed. Consult [current pricing](https://cloud.laravel.com/pricing); do not promise free or fixed-cost hosting. The [trial](https://laravel.com/cloud/docs/free-trial) has limits.

If the user has no account, guide them to [Laravel Cloud](https://cloud.laravel.com) to sign up, verify their account, choose a plan, and supply any requested payment details. The user handles passwords, payment information, and identity checks. An agent can guide this flow but cannot substitute CLI calls for account creation.

First check existing CLI authorization and repository access. Do not ask an already authorized user to sign into Cloud just because the browser is logged out. Only if repository access is missing, use **Account settings → Source controls** to connect GitHub and authorize Cloud's GitHub App for the repository to deploy. A public repository or successful `gh auth` does not grant Cloud access. See [source control setup](https://laravel.com/cloud/docs/source-control).

## 2. Install and authenticate the tools

Check `php --version`, `composer --version`, `git --version`, `node --version`, and `npm --version`. Use Node 22 for this starter. The audited CLI package requires **PHP 8.3+**; Composer checks the actual installed release's requirements. If PHP or Composer is absent, use the platform's normal installer and [Composer's installation instructions](https://getcomposer.org/download/). Do not execute an unverified installer copied from a third-party page.

```sh
composer global require laravel/cloud-cli
export PATH="$(composer global config bin-dir --absolute):$PATH"
cloud --version -n
cloud auth -h -n
# Only if no valid token is already available:
cloud auth -n
```

Before authenticating, run `cloud auth:token --list --json -n` and verify the intended organization. Reuse valid credentials. Check the actual `node --version`; a directory named `node@22` is not proof of its version.

Persist the Composer bin path in the user's shell configuration if needed. `cloud auth -n` still requires browser authorization; `-n` disables terminal questions, not OAuth consent. Wait for authorization to finish. If localhost callback authentication fails, inspect the error and PHP sockets support or use a token.

For a headless machine, the user can create an organization API token in Cloud following [API authentication](https://laravel.com/cloud/docs/api/authentication). Pass it through a protected local file or secret manager, never chat:

```sh
cloud auth:token -h -n
cloud auth:token --add -n < /absolute/path/to/protected-token-file
cloud auth:token --list --json -n
```

Keep the default masking enabled. The token needs permission for the resources this guide manages. `LARAVEL_CLOUD_TOKEN` overrides saved tokens; check whether it is set without printing its value. Never dump `~/.config/cloud/config.json`.

With multiple organizations, select the intended one before creating anything. In an organization with an existing app, `cloud repo:config EXISTING_APP_ID --organization=ORG_ID -n` establishes repository-local defaults. With no existing app and multiple saved tokens, supply only the intended organization's token through `LARAVEL_CLOUD_TOKEN` in a protected process environment; do not delete other saved tokens. After creating the backend, configure its repository defaults using its ID.

## 3. Prepare the repository and discover commands

Fork the starter into the user's GitHub account if they want to customize it, or deploy the original repository directly. Clone the selected repository locally. Preserve both `package-lock.json` files: [Cloud detects Node projects from the lockfile](https://laravel.com/cloud/docs/runtimes). Cloud's default Node version may differ from the tested Node 22.

Run commands from that checkout. Ignore `.cloud/` and secret files. Use explicit resource IDs throughout; backend and dashboard are separate applications even though they share a repository.

Before using a command, run `cloud COMMAND -h -n`. Use `--json -n` for resource reads and creates, `--json -n --force` for updates, and `-n --force` for environment variables. Deploy/monitor with `-n`. Check exit status, parse the returned JSON structure, and save IDs; do not assume response shapes or derive IDs from names.

Read/list existing resources before creating them. If a create command times out, check whether it succeeded before retrying. Reuse only resources that belong to this deployment. Never remove unrelated resources as cleanup.

Do not use `cloud ship` for this recipe: it deploys before this guide's custom runtime and persistent-storage configuration is complete.

## 4. Create the backend and persistent resources

The following examples use shell variables populated from the user's choices and prior command results. They are individual steps, not a script to paste before those variables are set. `REPOSITORY` is `owner/repo`, `REGION` is a supported Cloud region, and `BACKEND_NAME` is the chosen application name.

```sh
cloud application:create --name="$BACKEND_NAME" --repository="$REPOSITORY" \
  --source-provider=github --region="$REGION" --json -n
cloud environment:list "$BACKEND_APP_ID" --json -n
```

Omit `--root-directory` for the backend. The UI's `/` means repository root, but the API expects null/omitted or a relative subdirectory. Do not pass `/` to the create command. If the desired environment is absent, create it:

```sh
cloud environment:create "$BACKEND_APP_ID" --name=production --branch=main --json -n
cloud repo:config "$BACKEND_APP_ID" --organization="$ORG_ID" -n
```

Use the chosen branch instead of `main` if different. Capture the backend environment ID and assigned public HTTPS URL. Inspect its existing app instance; configure that instance rather than accidentally adding a replica. If no app instance exists, discover `instance:create` help and create one with the chosen size.

Choose an instance identity such as `convex`. Its MySQL database must be named `convex`; `my-convex` would require `my_convex`.

```sh
cloud database-cluster:create --name="$DATABASE_CLUSTER_NAME" \
  --type=laravel_mysql --engine-version=8.4 --region="$REGION" --json -n
cloud database:list "$DATABASE_CLUSTER_ID" --json -n
# Only if the required schema does not already exist:
cloud database:create "$DATABASE_CLUSTER_ID" --name=convex --json -n
cloud environment:update "$BACKEND_ENV_ID" --database-id="$DATABASE_ID" \
  --build-command='bash build.sh' --deploy-command='' --json -n --force
```

Check currently available engine versions and region support before creating the cluster. In v0.6.1, noninteractive `database-cluster:create` selects its default **Dev** preset (private, 512 MiB, 5 GB storage). There is no preset/size flag on this command. This is an audited CLI default, not a production sizing recommendation. If it does not fit the agreed budget or capacity, configure the cluster in Cloud's UI before proceeding. Do not confuse database RAM with the backend's 2 GB RAM. Wait for the cluster to report ready via `database-cluster:get` **before** calling `database:create`. The test failed schema creation while the cluster was still provisioning. Poll with a bounded timeout; after any timeout list schemas before retrying creation. Then wait for the schema before deployment.

Create the bucket with read/write access:

```sh
cloud bucket:create --name="$BUCKET_NAME" --visibility=private \
  --jurisdiction=default --key-name=convex --key-permission=read_write \
  --allowed-origins="$BACKEND_URL" --json -n
```

The tested CLI requires `--allowed-origins` in noninteractive mode. Use the actual backend origin here; this bucket setting does not configure Convex WebSocket CORS.

Use `eu` instead of `default` if the agreed storage jurisdiction requires it. The audited command advertises `--region` but does not send it in its bucket-create request; do not promise application-region placement from that flag. Keep credentials masked and record the bucket/key IDs for attachment.

Select `BACKEND_SIZE` from `cloud instance:sizes --json -n` after checking its help. Use an available 1 GB option; do not copy a legacy size ID just because it appears in Lawn or the test record.

```sh
cloud instance:update "$BACKEND_INSTANCE_ID" --size="$BACKEND_SIZE" \
  --scaling-type=none --json -n --force
```

Keep exactly one backend replica. The [cost guide](../costs.md) explains the two sleep profiles. Cloud instance timeouts are **minutes**; MySQL suspend timeouts are **seconds**.

## 5. Configure the remaining settings from the terminal

The successful standalone test used Cloud's generated startup configuration, which runs the committed `package.json` start script. Root `npm start` runs `bash start.sh`; the dashboard has its own start script. The demo frontend runs Nitro. Do not block on browser sign-in to set a redundant custom start command.

Use [scripts/cloud-api.py](../../scripts/cloud-api.py) for Node version, push-to-deploy, bucket attachment, and effective hibernation settings. It requires Python 3 and curl, reuses `LARAVEL_CLOUD_TOKEN` or exactly one saved CLI token, and checks the expected organization **before** accessing a resource. With multiple saved tokens, select one through a protected process environment; it deliberately does not guess. It prints only selected settings and resource relationships, withholding API error bodies and credentials.

First inspect the target and its existing bucket attachments:

```sh
python3 scripts/cloud-api.py GET "environments/$BACKEND_ENV_ID?include=instances,buckets" \
  --organization="$ORG_ID"
```

Prepare a local JSON file with these fields (replace the example key ID with the bucket's actual **key ID**, not its bucket ID):

```json
{
  "node_version": "22",
  "uses_push_to_deploy": false,
  "filesystem_keys": [
    {"id": "YOUR_BUCKET_KEY_ID", "disk": "s3", "is_default_disk": true}
  ]
}
```

Create the ignored `.cloud/` directory if needed. Save it as `.cloud/backend-settings.json`, then:

```sh
python3 scripts/cloud-api.py PATCH "environments/$BACKEND_ENV_ID" \
  --organization="$ORG_ID" --data-file=.cloud/backend-settings.json
```

This attachment example is for a **new backend with no other buckets**. `filesystem_keys` replaces the attachment list; preserve existing attachments when updating an existing environment. An empty array detaches all buckets. Use the Cloud UI if the existing key/disk mapping cannot be determined safely. Do not attach storage to the dashboard or frontend; their JSON only needs `node_version` and `uses_push_to_deploy`.

For the low-cost demo, save `{"hibernation_timeout":5}` as `.cloud/instance-settings.json`. For the always-on backend, use `{"hibernation_timeout":null}` instead. Then:

```sh
python3 scripts/cloud-api.py PATCH "instances/$BACKEND_INSTANCE_ID" \
  --organization="$ORG_ID" --data-file=.cloud/instance-settings.json
python3 scripts/cloud-api.py GET "environments/$BACKEND_ENV_ID?include=instances,buckets" \
  --organization="$ORG_ID"
```

Read back Node 22, one instance, expected timeout, and the private bucket relationship. Confirm database attachment and injected variable **names**, without revealing values. For hosted dashboard/frontend, use their own IDs and five-minute hibernation when appropriate.

For eligible MySQL, inspect `database-cluster:update -h -n`; the test successfully used `--suspend-seconds=300` despite help labeling it Neon. Read back `config.suspend_seconds`. Preserve size, storage, private access, and backup settings. Use `0` for no database sleep. An idle Convex process may hold connections and prevent MySQL sleep; configured timeouts alone do not establish actual savings.

If an API call fails, inspect its HTTP status, current docs, and CLI resource state. Do not guess undocumented fields or retry blindly. The Cloud UI remains a fallback if API access is unavailable. User browser interaction is still needed for a new account, billing, OAuth consent, or missing GitHub authorization.

## 6. Set backend variables without leaking secrets

Set `INSTANCE_NAME`, a stable `INSTANCE_SECRET`, `CONVEX_CLOUD_ORIGIN`, `CONVEX_BACKEND_VERSION`, and `DB_CONNECTION=mysql` using the values in the [backend guide](../../README.md#3-configure-the-backend-environment). `CONVEX_CLOUD_ORIGIN` must be the actual backend URL, not the dashboard URL. Leave `PORT` and the injected database/bucket credentials to Cloud.

For non-secret values:

```sh
cloud environment:variables "$BACKEND_ENV_ID" --action=set \
  --key=INSTANCE_NAME --value=convex -n --force
cloud environment:variables "$BACKEND_ENV_ID" --action=set \
  --key=CONVEX_CLOUD_ORIGIN --value="$BACKEND_URL" -n --force
cloud environment:variables "$BACKEND_ENV_ID" --action=set \
  --key=CONVEX_BACKEND_VERSION --value=precompiled-2026-09-26-27ef234 -n --force
cloud environment:variables "$BACKEND_ENV_ID" --action=set \
  --key=DB_CONNECTION --value=mysql -n --force
```

Generate `INSTANCE_SECRET` once with `openssl rand -hex 32` into protected local storage, without echoing it to the agent transcript. Back it up securely. Set it through Cloud's secret input or a protected subprocess calling `environment:variables --action=set --key=INSTANCE_SECRET --value=...`. v0.6.1 has no stdin value option for this command; values passed as arguments can appear in local process inspection. Disable shell tracing and never put a literal secret into a logged command. Do not regenerate an existing instance's secret during a retry.

For the private Cloud MySQL endpoint used by this recipe, also set `DO_NOT_REQUIRE_SSL=1`, after reading the [TLS workaround and its scope](../../README.md#cloud-mysql-connection-setting). It disables database-connection TLS and is not appropriate for public/external MySQL. Remove stale `POSTGRES_URL`/`MYSQL_URL` overrides when using attached DB variables. Never expose `INSTANCE_SECRET` or the admin key as a `VITE_*` or `NEXT_PUBLIC_*` variable.

## 7. Deploy, monitor, and generate the admin key

Only proceed after persistence, runtime settings, identity, and public origin are configured.

```sh
cloud deploy "$BACKEND_APP_ID" production -n
cloud deploy:monitor "$BACKEND_APP_ID" production -n
curl --fail --show-error "$BACKEND_URL/version"
```

Substitute the selected environment **name** in deploy commands; resource-update commands above use its **ID**. Check startup logs for `db=mysql-v5`, S3 storage, and the IPv6 proxy. HTTP 200 from `/version` is expected; `unknown` version text is allowed for this binary. This is only an availability check.

Generate the admin key with the deployed backend, keeping the remote shell variables literal in the local command:

```sh
cloud command:run "$BACKEND_ENV_ID" \
  --cmd='./bin/convex-local-backend keygen admin-key --instance-name "$INSTANCE_NAME" --instance-secret "$INSTANCE_SECRET"' -n
```

**This command returns a secret.** Run it in a protected terminal or capture output directly to a protected file, not a shared agent transcript. Cloud operators may also see the command output. Save the key in the user's secret manager for CLI deployment and dashboard login.

On deployment failure, inspect the error and current resource state, fix the cause, and monitor the next deployment. Do not repeatedly deploy unchanged configuration or delete storage to fix startup.

## 8. Optional dashboard and application

Create another application from the same repository with `--root-directory=dashboard`. Reuse the chosen region, and create or select its environment as above. Set its build command to `npm run build`, blank deploy commands, and Node 22. Cloud uses its `npm start` script automatically. The standalone test used 512 MB with five-minute hibernation. Set `NEXT_PUBLIC_DEPLOYMENT_URL` to the backend URL **before building**. Do not set `NEXT_PUBLIC_ADMIN_KEY`. The dashboard needs neither MySQL nor a bucket. Follow the [dashboard README](../../dashboard/README.md), then deploy and monitor with the dashboard app ID.

The backend infrastructure repo contains no application functions. For a small anonymous example, use [convex-cloud-demo](https://github.com/joshcirre/convex-cloud-demo) and follow its README after this backend is ready. Deploy them from the user's separate application project using an ignored `.env.self-hosted` containing `CONVEX_SELF_HOSTED_URL` and `CONVEX_SELF_HOSTED_ADMIN_KEY`. Set required Convex function environment variables before `npx convex deploy --env-file .env.self-hosted`. Use the backend-compatible CLI version from the backend README. Then build/deploy the frontend with only its public backend URL.

Do not run bare `convex dev` against this project: an upstream template may onboard to Convex's hosted service instead. For development use `convex dev --env-file .env.self-hosted` against a separate development instance. Keep admin credentials out of browser bundles.

## 9. Prove the deployment and hand it off

A successful build is insufficient. Record each result:

- Backend `/version` returns 200, with MySQL/S3 startup confirmed and no repeated restarts.
- Deploy the application's functions, perform a mutation, and read the result back.
- Open the frontend in two sessions and verify a live update without refresh; inspect the WebSocket connection if it fails.
- If requested, log into the hosted dashboard with the admin key and inspect the same data. Its URL must target the correct backend.
- Redeploy the backend, monitor recovery, and verify that the saved data and deployed functions remain available. If the demo exercises file storage, verify an uploaded file too.
- Recheck one backend instance, the chosen hibernation profile, private database/bucket, and absence of admin keys in public client configuration.

Report the repository revision, CLI version, organization/resource IDs, public URLs, test results, and remaining steps. Separate locally checked behavior from live Cloud checks. Record secret **locations**, never their values. Back up the stable instance identity and document database/object-storage backup arrangements before using this as a production service. Leave failed resources documented for review; do not silently delete billed resources or data.

## Audit boundary

On September 28, 2026 an independent agent deployed this standalone starter using existing Cloud/GitHub access: 1 GB backend, 512 MB dashboard, private MySQL and bucket, then a 512 MB hosted demo frontend. Function deployment, WebSocket connection, two-tab updates, dashboard login, query/mutation/action, and data/function persistence after a backend redeploy passed. The new API helper has unit coverage and a live read-only check; its PATCH payloads reproduce those used in that deployment but have not been replayed through this helper against a fresh deployment.

New-account onboarding, 512 MB backend operation, sleep/wake timing, load testing, uploaded-file persistence, backup recovery, and realized monthly bills remain unverified. Do not label configured scale-to-zero as tested sleep/wake behavior.
