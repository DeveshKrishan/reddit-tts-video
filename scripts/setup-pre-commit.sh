#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v pre-commit >/dev/null 2>&1; then
  echo "pre-commit is required: pip install pre-commit"
  exit 1
fi

pre-commit install

echo "Installed pre-commit and commit-msg hooks (commitlint runs on every commit)."
echo "First commitlint run downloads Node deps into ~/.cache/pre-commit."
