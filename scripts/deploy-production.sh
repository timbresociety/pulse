#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
production_domain="psyblr.vercel.app"
production_url="https://$production_domain"

cd "$repo_root"

if [[ "${CONFIRM_PRODUCTION_DEPLOY:-}" != "$production_domain" ]]; then
  echo "Production deployment is locked." >&2
  echo "Set CONFIRM_PRODUCTION_DEPLOY=$production_domain only after explicit approval." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to deploy: the working tree is not clean." >&2
  git status --short >&2
  exit 1
fi

branch="$(git branch --show-current)"
if [[ "$branch" != "main" ]]; then
  echo "Refusing to deploy: production releases must come from main, not $branch." >&2
  exit 1
fi

git fetch --quiet origin main
if [[ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]]; then
  echo "Refusing to deploy: local main does not exactly match origin/main." >&2
  exit 1
fi

"$repo_root/scripts/verify-release.sh"

echo "Auditing the Vercel upload manifest..."
dry_run_json="$(npx vercel deploy --dry --json --cwd "$repo_root")"
printf '%s' "$dry_run_json" | node -e '
  let input = "";
  process.stdin.on("data", chunk => input += chunk);
  process.stdin.on("end", () => {
    const value = JSON.parse(input);
    const paths = (value.files || []).map(file => file.path);
    const forbidden = paths.filter(path =>
      /(^|\/)\.env$/.test(path) ||
      /(^|\/)\.env\.local$/.test(path) ||
      /(^|\/)\.env\..*\.local$/.test(path) ||
      /(^|\/)\.vercel(\/|$)/.test(path) ||
      /(^|\/)\.venv(\/|$)/.test(path) ||
      /(^|\/)node_modules(\/|$)/.test(path) ||
      /(^|\/)dist(\/|$)/.test(path) ||
      /(^|\/)\.pytest_cache(\/|$)/.test(path) ||
      /(^|\/)__pycache__(\/|$)/.test(path)
    );
    if (forbidden.length) {
      console.error(`Refusing to deploy forbidden local files:\n${forbidden.join("\n")}`);
      process.exit(1);
    }
  });
'

previous_json="$(npx vercel inspect "$production_url" --json --cwd "$repo_root")"
previous_deployment="$(printf '%s' "$previous_json" | node -e '
  let input = "";
  process.stdin.on("data", chunk => input += chunk);
  process.stdin.on("end", () => {
    const value = JSON.parse(input);
    const url = value.url || value.deployment?.url;
    if (!url) process.exit(1);
    process.stdout.write(url);
  });
')"

echo "Building an unaliased production deployment..."
deployment_json="$(
  npx vercel deploy \
    --prod \
    --skip-domain \
    --yes \
    --json \
    --meta releaseCommit="$(git rev-parse HEAD)" \
    --meta releaseGuarded=1 \
    --cwd "$repo_root"
)"
deployment_url="$(printf '%s' "$deployment_json" | node -e '
  let input = "";
  process.stdin.on("data", chunk => input += chunk);
  process.stdin.on("end", () => {
    const value = JSON.parse(input);
    const deploymentUrl = value.url || value.deployment?.url;
    if (!deploymentUrl) process.exit(1);
    const url = deploymentUrl.startsWith("http") ? deploymentUrl : `https://${deploymentUrl}`;
    process.stdout.write(url);
  });
')"

echo "Testing the new deployment before changing the live domain..."
"$repo_root/scripts/smoke-production.sh" "$deployment_url"

echo "Promoting the verified deployment..."
npx vercel promote "$deployment_url" --yes --cwd "$repo_root"

if ! "$repo_root/scripts/smoke-production.sh" "$production_url"; then
  echo "Live smoke test failed; rolling back to $previous_deployment." >&2
  npx vercel rollback "$previous_deployment" --yes --cwd "$repo_root"
  exit 1
fi

echo "Production release completed successfully: $production_url"
