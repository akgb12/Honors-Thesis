#!/usr/bin/env bash
# Prepare a reusable uv environment on macOS
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"

if [ -L .venv ]; then
  if [ "$(readlink .venv)" != "venv" ]; then
    echo "Expected .venv to point to venv"
    exit 1
  fi
elif [ -d .venv ]; then
  if [ -e venv ]; then
    echo "Cannot move .venv because venv already exists"
    exit 1
  fi
  mv .venv venv
  ln -s venv .venv
elif [ -e .venv ]; then
  echo "Expected .venv to be a directory or symbolic link"
  exit 1
elif [ -d venv ]; then
  ln -s venv .venv
else
  UV_PROJECT_ENVIRONMENT=venv uv sync
  ln -s venv .venv
fi

if command -v chflags >/dev/null 2>&1; then
  chflags -R nohidden venv
fi

uv sync
