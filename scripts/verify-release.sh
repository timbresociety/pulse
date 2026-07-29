#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -x "$repo_root/backend/.venv/bin/python" ]]; then
  backend_python="$repo_root/backend/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  backend_python="$(command -v python3)"
else
  echo "Python 3 is required to run the backend tests." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to build the frontend." >&2
  exit 1
fi

echo "Running backend tests..."
(
  cd "$repo_root/backend"
  "$backend_python" -m pytest -q
)

echo "Building frontend..."
(
  cd "$repo_root/frontend"
  npm run build
)

echo "Release verification passed."
