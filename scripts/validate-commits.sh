#!/usr/bin/env bash
set -euo pipefail

FROM="${1:-main}"
TO="${2:-HEAD}"

if ! command -v pre-commit >/dev/null 2>&1; then
  echo "pre-commit is required: pip install pre-commit"
  exit 1
fi

pre-commit install --hook-type commit-msg >/dev/null

empty=1
for sha in $(git rev-list --reverse "$FROM..$TO" 2>/dev/null); do
  empty=0
  msg_file=$(mktemp)
  git log -1 --format=%B "$sha" > "$msg_file"
  if ! pre-commit run commitlint --hook-stage commit-msg --commit-msg-filename "$msg_file"; then
    rm -f "$msg_file"
    echo
    echo "Failed commit: $sha $(git log -1 --format=%s "$sha")"
    echo "Tip: commit body lines must be <= 100 characters (wrap long lines)."
    exit 1
  fi
  rm -f "$msg_file"
done

if [ "$empty" -eq 1 ]; then
  echo "No commits between $FROM and $TO"
fi
