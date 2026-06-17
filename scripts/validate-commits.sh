#!/usr/bin/env bash
set -euo pipefail

FROM="${1:-main}"
TO="${2:-HEAD}"

if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required to run commitlint"
  exit 1
fi

npx --yes @commitlint/cli@19 --config commitlint.config.cjs --from "$FROM" --to "$TO"
