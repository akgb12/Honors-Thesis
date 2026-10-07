#!/usr/bin/env bash
# Installs a local pre-commit hook that runs scripts/check_staged_secrets.sh.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
hook="$root/.git/hooks/pre-commit"
cat > "$hook" <<'HOOK'
#!/usr/bin/env bash
exec "$(git rev-parse --show-toplevel)/scripts/check_staged_secrets.sh"
HOOK
chmod +x "$hook" "$root/scripts/check_staged_secrets.sh"
echo "Installed $hook"
