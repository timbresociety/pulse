#!/usr/bin/env bash
set -euo pipefail

base_url="${1:-https://psyblr.vercel.app}"
base_url="${base_url%/}"

if [[ "$base_url" != https://* ]]; then
  echo "Smoke-test URL must use HTTPS: $base_url" >&2
  exit 1
fi

work_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$work_dir"
}
trap cleanup EXIT

curl_json() {
  local path="$1"
  local output="$2"
  if [[ "${VERCEL_AUTHENTICATED_SMOKE:-false}" == "true" ]]; then
    npx vercel curl "$path" \
      --deployment "$base_url" \
      -- \
      --http1.1 \
      --fail \
      --show-error \
      --silent \
      --location \
      --max-time 30 \
      --retry 3 \
      --retry-all-errors \
      --retry-delay 2 \
      --output "$output"
  else
    curl \
      --http1.1 \
      --fail \
      --show-error \
      --silent \
      --location \
      --max-time 30 \
      --retry 3 \
      --retry-all-errors \
      --retry-delay 2 \
      "$base_url$path" \
      --output "$output"
  fi
}

echo "Checking frontend..."
curl_json "/" "$work_dir/index.html"
if ! grep -q '<div id="root"' "$work_dir/index.html"; then
  echo "Frontend smoke test failed: React root was not found." >&2
  exit 1
fi

echo "Checking frontend reload routes..."
for route in /categories /feed /reveals /history /wallet /social /leaderboard /profile; do
  curl_json "$route" "$work_dir/route.html"
  if ! grep -q '<div id="root"' "$work_dir/route.html"; then
    echo "Frontend smoke test failed at $route: React root was not found." >&2
    exit 1
  fi
done

echo "Checking API liveness..."
curl_json "/api/health" "$work_dir/health.json"
node -e '
  const fs = require("fs");
  const value = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  if (value.status !== "ok" || value.debug !== false) process.exit(1);
' "$work_dir/health.json"

echo "Checking database readiness..."
curl_json "/api/ready" "$work_dir/ready.json"
node -e '
  const fs = require("fs");
  const value = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  if (value.status !== "ready") process.exit(1);
' "$work_dir/ready.json"

echo "Checking database-backed catalog..."
curl_json "/api/categories" "$work_dir/categories.json"
node -e '
  const fs = require("fs");
  const value = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  if (!Array.isArray(value) || value.length === 0) process.exit(1);
' "$work_dir/categories.json"

echo "Production smoke tests passed for $base_url."
