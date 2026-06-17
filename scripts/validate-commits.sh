#!/usr/bin/env bash
set -euo pipefail

FROM="${1:-main}"
TO="${2:-HEAD}"

if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required to run commitlint"
  exit 1
fi

npx --yes -p @commitlint/cli@19 -p @commitlint/config-conventional@19 \
  commitlint --config commitlint.config.cjs --from "$FROM" --to "$TO"
