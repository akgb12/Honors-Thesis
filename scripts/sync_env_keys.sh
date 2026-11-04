#!/usr/bin/env bash
# Appends keys that exist in .env.example but are missing from .env.
# Never prints or reads VALUES from .env (it only checks whether a key name is present).
# Local-only placeholders are used for the two storage credentials, which are meaningless
# for a local SeaweedFS with auth off. Replace them with real credentials when moving to S3.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
cd "$root"
[ -f .env.example ] || { echo ".env.example not found"; exit 1; }
[ -f .env ] || touch .env
added=0
while IFS= read -r line; do
  case "$line" in ''|'#'*) continue ;; esac
  key="${line%%=*}"
  if ! grep -q "^${key}=" .env; then
    case "$key" in
      AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY) line="${key}=local-dev" ;;
    esac
    printf '%s\n' "$line" >> .env
    echo "added key: $key"
    added=$((added + 1))
  fi
done < .env.example
echo "$added key(s) added to .env"
