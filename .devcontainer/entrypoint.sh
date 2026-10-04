#!/bin/bash
# Container start: configure git identity, sync the environment, stay alive.
set -euo pipefail

cd /app

# The bind-mounted repo is owned by the host user, not by `developer`. Guarded
# rather than unconditional: --add appends on every start, and a plain
# `docker start` would otherwise accumulate duplicate entries.
# /app/.git is listed separately on purpose: git checks the exact path, and
# tools that clone the repo from inside the container (`copier update`, for one)
# ask about /app/.git rather than /app, and fail with "dubious ownership" if only
# /app is exempt.
for d in /app /app/.git; do
  if ! git config --global --get-all safe.directory 2>/dev/null | grep -qx "${d}"; then
    git config --global --add safe.directory "${d}"
  fi
done

if [ -n "${GIT_AUTHOR_NAME:-}" ] && [ -n "${GIT_AUTHOR_EMAIL:-}" ]; then
  git config --global user.name "${GIT_AUTHOR_NAME}"
  git config --global user.email "${GIT_AUTHOR_EMAIL}"
else
  echo "GIT_AUTHOR_NAME and GIT_AUTHOR_EMAIL not set; skipping git identity config"
  echo "Set them in .devcontainer/.env, or run git config --global user.name/user.email"
fi

if [ -f pyproject.toml ]; then
  # A Windows bind mount can present uv.lock as read-only. Sync from it without
  # writing instead of deleting it: the previous behaviour discarded every
  # pinned version to work around a permission bug.
  #
  # The `! -f` arm matters. `[ -w uv.lock ]` is also false when the file does not
  # exist, so without it a fresh clone would take the --frozen path and fail on a
  # missing lockfile.
  if [ ! -f uv.lock ] || [ -w uv.lock ]; then
    sync_cmd=(uv sync --all-groups)
  else
    echo "uv.lock is read-only; syncing with --frozen (the lock will not be updated)"
    sync_cmd=(uv sync --frozen --all-groups)
  fi

  # Deliberately non-fatal. Under `set -e` a transient failure here (no network
  # on first start, a package index outage) would abort this script and kill the
  # container, leaving the user with no way to shell in and diagnose.
  if ! "${sync_cmd[@]}"; then
    echo "WARNING: uv sync failed. The container is still running so you can"
    echo "         attach and re-run 'uv sync --all-groups' once the cause is fixed."
  fi
else
  echo "pyproject.toml not found; skipping uv sync"
fi

# Install the git hooks here rather than from a devcontainer postCreateCommand,
# so that `docker compose up` on its own produces a complete environment and
# devcontainer.json stays a thin editor wrapper over this file. Guards that
# postCreateCommand got for free:
#   - no .git yet: a freshly generated project before `git init`
#   - no config: a project that does not use pre-commit
#   - non-fatal: a failure here must not take the container down with it
if [ -d .git ] && [ -f .pre-commit-config.yaml ]; then
  if ! uv run --frozen pre-commit install --install-hooks; then
    echo "WARNING: pre-commit install failed; git hooks are NOT active."
    echo "         Re-run 'uv run pre-commit install --install-hooks' once fixed."
  fi
else
  echo "No .git or no .pre-commit-config.yaml; skipping pre-commit install"
fi

exec sleep infinity
