#!/usr/bin/env bash
# Fills the CHANGEME values in .env for a fresh clone:
#   - generates Langfuse secrets (NEXTAUTH_SECRET, SALT, ENCRYPTION_KEY, database, ClickHouse, Redis, MinIO, admin password);
#   - generates the first project's key pair and writes it to LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY.
# Langfuse creates the org, project, user and keys from LANGFUSE_INIT_* on its first boot, when its database is empty.
# Run it once, before `docker compose up -d`. It leaves values that are already set alone, so it can be re-run safely.
# Keys are project keys: Langfuse self-hosted keys are not read-only, so keep .env private.
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="${ENV_FILE:-.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found. Run: cp .env.example $ENV_FILE" >&2
  exit 1
fi
command -v openssl >/dev/null || { echo "error: openssl is required" >&2; exit 1; }

# Current value of KEY in .env, or empty.
get_var() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true
}

# Sets KEY=VALUE in .env, replacing the line if present, appending otherwise. Values are hex or
# prefixed ids, so | is a safe sed delimiter.
set_var() {
  local key="$1" value="$2" tmp
  tmp="$(mktemp "${ENV_FILE}.XXXXXX")"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -E "s|^${key}=.*$|${key}=${value}|" "$ENV_FILE" > "$tmp"
  else
    cat "$ENV_FILE" > "$tmp"
    printf '%s=%s\n' "$key" "$value" >> "$tmp"
  fi
  chmod 600 "$tmp"
  mv "$tmp" "$ENV_FILE"
}

# Generates a value for KEY unless .env already holds a real one (empty or CHANGEME means unset).
ensure() {
  local key="$1" generator="$2" current
  current="$(get_var "$key")"
  if [[ -z "$current" || "$current" == "CHANGEME" ]]; then
    set_var "$key" "$("$generator")"
    echo "generated $key"
  fi
}

hex32() { openssl rand -hex 32; }
hex16() { openssl rand -hex 16; }
pw() { openssl rand -hex 24; }
pk() { printf 'pk-lf-%s' "$(hex16)"; }
sk() { printf 'sk-lf-%s' "$(hex16)"; }
id() { printf 'tripwire-%s' "$(hex16)"; }

ensure NEXTAUTH_SECRET hex32
ensure SALT hex32
ensure ENCRYPTION_KEY hex32
ensure POSTGRES_PASSWORD pw
ensure CLICKHOUSE_PASSWORD pw
ensure REDIS_AUTH pw
ensure MINIO_ROOT_PASSWORD pw
ensure LANGFUSE_INIT_USER_PASSWORD pw
ensure LANGFUSE_INIT_ORG_ID id
ensure LANGFUSE_INIT_PROJECT_ID id
ensure LANGFUSE_INIT_PROJECT_PUBLIC_KEY pk
ensure LANGFUSE_INIT_PROJECT_SECRET_KEY sk

# The detector and the demo agent use the project keys created above.
for pair in "LANGFUSE_PUBLIC_KEY:LANGFUSE_INIT_PROJECT_PUBLIC_KEY" "LANGFUSE_SECRET_KEY:LANGFUSE_INIT_PROJECT_SECRET_KEY"; do
  target="${pair%%:*}"
  source="${pair##*:}"
  current="$(get_var "$target")"
  if [[ -z "$current" || "$current" == "CHANGEME" ]]; then
    set_var "$target" "$(get_var "$source")"
    echo "copied $source to $target"
  fi
done

echo "done: $ENV_FILE is ready. Next: docker compose up -d"
echo "Langfuse UI: http://127.0.0.1:3000 (login: $(get_var LANGFUSE_INIT_USER_EMAIL))"
