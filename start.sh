#!/usr/bin/env bash
#
# Laravel Cloud start command for the self-hosted Convex backend.
#
# Maps Cloud's injected env (DATABASE_URL, AWS_* from an attached bucket, PORT)
# onto convex-local-backend flags. Modeled on the official Docker entrypoint:
# github.com/get-convex/convex-backend/blob/main/self-hosted/docker-build/run_backend.sh
#
# Cloud gives each app a single port, so HTTP actions (Stripe/Mux webhooks) are
# served from the same origin under /http instead of a second port.
#
# Required env:
#   INSTANCE_NAME        e.g. convex. SQL database must be named the same
#                        with "-" -> "_" (the admin key is derived from it too).
#   INSTANCE_SECRET      64 hex chars (openssl rand -hex 32). Never let it
#                        default: the disk is ephemeral.
#   CONVEX_CLOUD_ORIGIN  public URL of this app, e.g. https://convex.example.com
#                        (falls back to APP_URL).
#
set -euo pipefail
cd "$(dirname "$0")"

fail() {
  echo "start: $*" >&2
  exit 1
}

[ -n "${INSTANCE_NAME:-}" ] || fail "INSTANCE_NAME is required"
[ -n "${INSTANCE_SECRET:-}" ] || fail "INSTANCE_SECRET is required"
# Cloud's UI stores strings: "0" and "false" must not enable these flags.
optional_flags=()
for setting in DISABLE_BEACON REDACT_LOGS_TO_CLIENT DO_NOT_REQUIRE_SSL; do
  case "${!setting:-}" in
    1 | true)
      case "$setting" in
        DISABLE_BEACON) optional_flags+=(--disable-beacon) ;;
        REDACT_LOGS_TO_CLIENT) optional_flags+=(--redact-logs-to-client) ;;
        DO_NOT_REQUIRE_SSL) optional_flags+=(--do-not-require-ssl) ;;
      esac
      ;;
    '' | 0 | false) ;;
    *) fail "$setting must be 1, true, 0, false, or unset" ;;
  esac
done
origin="${CONVEX_CLOUD_ORIGIN:-${APP_URL:-}}"
[ -n "$origin" ] || fail "CONVEX_CLOUD_ORIGIN (or APP_URL) is required"
origin="${origin%/}"
site="${CONVEX_SITE_ORIGIN:-$origin/http}"

port="${PORT:-3000}"
# convex-local-backend can only bind IPv4, but Cloud reaches the app over IPv6,
# so the backend listens on loopback and proxy.mjs serves [::]:$PORT in front.
backend_port="${CONVEX_BACKEND_PORT:-$((port + 10))}"
# Internal only; Cloud's proxy never routes to it.
site_port="${CONVEX_SITE_PROXY_PORT:-$((backend_port + 1))}"

data_dir="${DATA_DIR:-/tmp/convex}"
export TMPDIR="${TMPDIR_OVERRIDE:-$data_dir/tmp}"
mkdir -p "$TMPDIR" "$data_dir/storage"

# --- persistence -------------------------------------------------------------
# Convex wants a server URL WITHOUT the database name or query params; it picks
# the database from INSTANCE_NAME. Cloud injects DATABASE_URL with both.
expected_db="${INSTANCE_NAME//-/_}"
# Cloud may inject Laravel-style DB_* vars instead of a URL; build one from them.
if [ -z "${DATABASE_URL:-}" ] && [ -n "${DB_HOST:-}" ]; then
  case "${DB_CONNECTION:-pgsql}" in
    pgsql | postgres | postgresql) db_scheme=postgres ;;
    mysql | mariadb) db_scheme=mysql ;;
    *) fail "unsupported DB_CONNECTION '${DB_CONNECTION}'" ;;
  esac
  db_user="$(node -p 'encodeURIComponent(process.env.DB_USERNAME ?? "")')"
  db_pass="$(node -p 'encodeURIComponent(process.env.DB_PASSWORD ?? "")')"
  DATABASE_URL="$db_scheme://$db_user:$db_pass@$DB_HOST${DB_PORT:+:$DB_PORT}/${DB_DATABASE:-}"
fi
db_flags=()
db_spec="$data_dir/db.sqlite3"
if [ -n "${POSTGRES_URL:-}" ]; then
  db_flags=(--db postgres-v5)
  db_spec="$POSTGRES_URL"
elif [ -n "${MYSQL_URL:-}" ]; then
  db_flags=(--db mysql-v5)
  db_spec="$MYSQL_URL"
elif [ -n "${DATABASE_URL:-}" ]; then
  scheme="${DATABASE_URL%%://*}"
  db_name="$(printf '%s' "$DATABASE_URL" | sed -E 's#^[a-z0-9+]+://[^/]+/?##; s#\?.*$##')"
  server="$(printf '%s' "$DATABASE_URL" | sed -E 's#^([a-z0-9+]+://[^/?]+).*#\1#')"
  if [ -n "$db_name" ] && [ "$db_name" != "$expected_db" ]; then
    fail "attached database is '$db_name' but INSTANCE_NAME=$INSTANCE_NAME expects '$expected_db'"
  fi
  case "$scheme" in
    postgres | postgresql) db_flags=(--db postgres-v5) ;;
    mysql) db_flags=(--db mysql-v5) ;;
    *) fail "unsupported DATABASE_URL scheme '$scheme'" ;;
  esac
  # Cloud Postgres hostnames (ep-x.c-N.aws-REGION.pg.laravel.cloud) are CNAMEs
  # to Neon, and Convex's TLS client ends up with Neon's certificate, which only
  # covers *.c-N.REGION.aws.neon.tech. Connect via the Neon name for the same
  # endpoint so verification passes.
  server="$(printf '%s' "$server" | sed -E 's#@([^.@/]+\.c-[0-9]+)\.aws-([a-z0-9-]+)\.pg\.laravel\.cloud#@\1.\2.aws.neon.tech#')"
  db_spec="$server"
else
  fail "attach MySQL or Postgres before starting: Cloud filesystem storage is ephemeral"
fi

# --- file storage ------------------------------------------------------------
# Cloud injects AWS_BUCKET / AWS_ENDPOINT_URL for the attached (R2) bucket.
# Convex wants five buckets; unless overridden they all share that bucket
# (Convex stores objects under generated keys, so they don't collide).
storage_flags=(--local-storage "$data_dir/storage")
if [ -n "${AWS_BUCKET:-}${S3_STORAGE_MODULES_BUCKET:-}" ]; then
  default_bucket="${AWS_BUCKET:-}"
  export S3_STORAGE_EXPORTS_BUCKET="${S3_STORAGE_EXPORTS_BUCKET:-$default_bucket}"
  export S3_STORAGE_SNAPSHOT_IMPORTS_BUCKET="${S3_STORAGE_SNAPSHOT_IMPORTS_BUCKET:-$default_bucket}"
  export S3_STORAGE_MODULES_BUCKET="${S3_STORAGE_MODULES_BUCKET:-$default_bucket}"
  export S3_STORAGE_FILES_BUCKET="${S3_STORAGE_FILES_BUCKET:-$default_bucket}"
  export S3_STORAGE_SEARCH_BUCKET="${S3_STORAGE_SEARCH_BUCKET:-$default_bucket}"
  export AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-auto}}"
  if [ -z "${S3_ENDPOINT_URL:-}" ]; then
    endpoint="${AWS_ENDPOINT_URL:-${AWS_ENDPOINT:-}}"
    [ -n "$endpoint" ] && export S3_ENDPOINT_URL="$endpoint"
  fi
  if [ -n "${S3_ENDPOINT_URL:-}" ]; then
    export AWS_S3_FORCE_PATH_STYLE="${AWS_S3_FORCE_PATH_STYLE:-true}"
  fi
  storage_flags=(--s3-storage)
else
  fail "attach a private bucket before starting: Cloud filesystem storage is ephemeral"
fi

node_version="$(node --version 2>/dev/null || true)"
case "$node_version" in
  v20.* | v22.* | v24.*) ;;
  *) echo "start: WARNING \"use node\" actions need node v20/v22/v24 on PATH (found '${node_version:-none}')." >&2 ;;
esac

echo "start: origin=$origin site=$site port=$port backend_port=$backend_port db=${db_flags[1]:-sqlite} db_host=${server:+${server##*@}} storage=${storage_flags[0]}"

bin/convex-local-backend \
  --instance-name "$INSTANCE_NAME" \
  --instance-secret "$INSTANCE_SECRET" \
  --interface 127.0.0.1 \
  --port "$backend_port" \
  --site-proxy-port "$site_port" \
  --convex-origin "$origin" \
  --convex-site "$site" \
  ${optional_flags[@]+"${optional_flags[@]}"} \
  ${db_flags[@]+"${db_flags[@]}"} \
  "${storage_flags[@]}" \
  "$db_spec" &
backend_pid=$!

LISTEN_PORT="$port" TARGET_PORT="$backend_port" node proxy.mjs &
proxy_pid=$!

# Stop both on SIGTERM (deploys/restarts), and exit as soon as either one dies
# so Cloud restarts the pair instead of leaving a half-working container.
stop() {
  kill "$backend_pid" "$proxy_pid" 2>/dev/null || true
  wait "$backend_pid" "$proxy_pid" 2>/dev/null || true
}
trap 'stop; exit 143' TERM INT
while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$proxy_pid" 2>/dev/null; do
  sleep 1
done
status=0
kill -0 "$backend_pid" 2>/dev/null || { wait "$backend_pid" || status=$?; echo "start: convex-local-backend exited ($status)" >&2; }
kill -0 "$proxy_pid" 2>/dev/null || { wait "$proxy_pid" || status=$?; echo "start: proxy exited ($status)" >&2; }
stop
# An unexpected successful child exit still leaves this service unavailable.
[ "$status" -ne 0 ] || status=1
exit "$status"
