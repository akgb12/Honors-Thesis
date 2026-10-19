#!/usr/bin/env bash
# Blocks commits that stage secrets, onboarding material, run output or large files.
# Used by .git/hooks/pre-commit (installed by scripts/install_git_hooks.sh).
set -uo pipefail

staged="$(git diff --cached --name-only --diff-filter=ACMR)"
[ -z "$staged" ] && exit 0
fail=0

# 1. Forbidden paths
while IFS= read -r f; do
  case "$f" in
    .env.example|*/.env.example) ;;
    .env|.env.*|*/.env|*/.env.*) echo "BLOCKED (env file): $f"; fail=1 ;;
    .onboarding/*|.cursor/*|.claude/*|CLAUDE.local.md|*/CLAUDE.local.md) echo "BLOCKED (local agent/onboarding material is never committed): $f"; fail=1 ;;
    runs/*|.cache/*|storage/*|*/storage/*) echo "BLOCKED (runtime output): $f"; fail=1 ;;
    *.pem|*.key|*.p12|*.pfx|id_rsa*|id_ed25519*) echo "BLOCKED (key material): $f"; fail=1 ;;
  esac
done <<< "$staged"

# 2. Secret-looking strings in added lines
added="$(git diff --cached -U0 | grep -E '^\+' | grep -vE '^\+\+\+' || true)"
if printf '%s\n' "$added" | grep -nE 'sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[baprs]-[A-Za-z0-9-]{10,}|gh[pousr]_[A-Za-z0-9]{30,}' >/dev/null; then
  echo "BLOCKED: a secret-like string is staged:"
  printf '%s\n' "$added" | grep -nE 'sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[baprs]-[A-Za-z0-9-]{10,}|gh[pousr]_[A-Za-z0-9]{30,}' | sed -E 's/(.{0,20}).*/\1…/'
  fail=1
fi

# 3. Secret-named variables given a value in env-style/config files
while IFS= read -r f; do
  case "$f" in
    *.env.example|*.ini|*.cfg|*.toml|*.yaml|*.yml|*.json)
      if git diff --cached -U0 -- "$f" | grep -E '^\+[^+]' | grep -qE '^\+[[:space:]]*"?[A-Z0-9_]*(API_KEY|SECRET|SECRET_KEY|TOKEN|PASSWORD|AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID)"?[[:space:]]*[=:][[:space:]]*"?[^"[:space:]]+'; then
        echo "BLOCKED: $f assigns a value to a secret-named variable"; fail=1
      fi ;;
  esac
done <<< "$staged"

# 4. Large files (> 2 MB)
while IFS= read -r f; do
  if [ -f "$f" ]; then
    size=$(( $(wc -c < "$f") ))
    if [ "$size" -gt 2000000 ]; then echo "BLOCKED (larger than 2 MB): $f"; fail=1; fi
  fi
done <<< "$staged"

if [ "$fail" -ne 0 ]; then
  echo "Commit blocked by scripts/check_staged_secrets.sh. Unstage the files above (git restore --staged <path>)."
fi
exit "$fail"
