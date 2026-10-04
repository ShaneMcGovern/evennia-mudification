# syntax=docker/dockerfile:1

# uv comes from its own image as a named build stage so the version is a literal
# FROM tag. Dependabot's docker ecosystem tracks FROM lines; an inline
# `COPY --from=ghcr.io/astral-sh/uv:X` is not reliably detected, which is why the
# previous pin sat at 0.9.26 long after 0.12.6 shipped.
FROM ghcr.io/astral-sh/uv:0.12.7 AS uv

FROM python:3.13.15-slim-bookworm

# Only packages something actually needs.
#
# ca-certificates and update-ca-certificates were both here and both no-ops. The
# base image already ships ca-certificates with a populated trust store, so apt
# reported "0 newly installed" and update-ca-certificates reported "0 added, 0
# removed". Reinstate them only if this image ever adds a custom CA.
#
# curl was here as "baseline developer tooling" with nothing using it. The Node
# hooks do not need it either: pre-commit's nodeenv downloads Node through
# Python, not curl. The template repo's own container has never installed curl
# and its Node hooks work.
#
# git: copier, pre-commit and entrypoint.sh all shell out to it.
# gh: GitHub CLI, authenticated through the persisted GH_CONFIG_DIR volume.
#   Debian bookworm freezes gh at 2.23.0 (Feb 2023) and no Dependabot ecosystem
#   can see an apt package, so this pin never moves. Accepted deliberately: the
#   alternative is GitHub's own apt repository, which reintroduces exactly the
#   keyring-and-source-list block removed with azure-cli. Enough for auth, repo,
#   and pr; swap to the upstream repo if a newer subcommand is needed.
# libatomic1: required by the Node runtime that pre-commit's nodeenv installs for
#   the prettier hook. The slim base image omits it, so without this the hook
#   fails to install with "libatomic.so.1: cannot open shared object file".
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gh \
        git \
        libatomic1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/

# UV_COMPILE_BYTECODE: pre-compile .pyc for faster interpreter startup.
# UV_LINK_MODE=copy: hard links fail across the bind-mount/volume boundary.
#
# VIRTUAL_ENV/PATH put the project environment ahead of the system interpreter,
# so a plain interactive shell finds pytest, ruff, and mypy and `python` is the
# project's. VS Code reads python.defaultInterpreterPath and the hooks use
# `uv run`, but a terminal has neither.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/app/.venv \
    PATH=/app/.venv/bin:$PATH

# ENV alone is not enough: a LOGIN shell sources /etc/profile, which rebuilds
# PATH from scratch and drops the venv. profile.d covers that case, so both
# `bash` and `bash -l` find the project tools.
RUN printf 'export VIRTUAL_ENV=/app/.venv\nexport PATH="/app/.venv/bin:${PATH}"\n' \
    > /etc/profile.d/10-venv.sh

# Non-root user; UID/GID 1000 is the dev container convention and the default
# here, so leaving these alone builds exactly the image it always did.
#
# The NAME is still a literal, and that part is not negotiable: compose.yaml
# hardcodes /home/developer for the cache volumes and GH_CONFIG_DIR, so a
# renamed user would leave those mounts pointing at a home that does not exist.
# A build arg that cannot safely be changed is worse than a literal.
#
# The NUMBERS are different, and used to be refused on the same grounds by
# mistake. Changing them keeps the name `developer` and the home
# /home/developer, so every hardcoded path in compose.yaml stays valid - the
# "half-applies" objection covers the name and not the numbers.
#
# They exist for Linux hosts. A bind mount passes UIDs through as raw numbers
# with no translation, so a host account that is not 1000 owns the repo as some
# other uid while this process runs as 1000: /app is readable but not writable,
# and the first thing to fail is pytest writing coverage.xml. Docker Desktop on
# Windows and macOS maps every file to the container user, so this cannot happen
# there and the defaults are all those hosts ever need.
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd --gid ${USER_GID} developer \
    && useradd --uid ${USER_UID} --gid ${USER_GID} --create-home --shell /bin/bash developer

# Matches compose.yaml working_dir and devcontainer.json workspaceFolder.
WORKDIR /app

# root-owned: executed by `developer`, which has no reason to be able to rewrite
# it.
COPY --chown=root:root --chmod=755 .devcontainer/entrypoint.sh /entrypoint.sh

# Every path compose.yaml mounts a named volume onto must already exist and be
# owned by the non-root user. Docker creates a missing mount target as
# root-owned, which would make `gh auth login`, `uv sync`, and pre-commit hook
# installation all fail with permission errors.
RUN mkdir -p /app/.venv \
        "/home/developer/.cache/uv" \
        "/home/developer/.cache/pre-commit" \
        "/home/developer/.config/gh" \
    && chown -R developer:developer \
        /app \
        "/home/developer/.cache" \
        "/home/developer/.config"

USER developer

ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
