#!/usr/bin/env bash
set -euo pipefail

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to run commitlint"
  exit 1
fi

if [ ! -d node_modules/@commitlint/cli ]; then
  npm install
fi

npx commitlint --config commitlint.config.cjs --edit "$1"
