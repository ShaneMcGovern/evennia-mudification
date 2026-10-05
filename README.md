# evennia-mudification

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.13.15](https://img.shields.io/badge/python-3.13.15-blue.svg)](https://www.python.org/downloads/)
[![Validate](https://github.com/ShaneMcGovern/evennia-mudification/actions/workflows/validate.yml/badge.svg?event=pull_request)](https://github.com/ShaneMcGovern/evennia-mudification/actions/workflows/validate.yml)
[![Coverage](badges/coverage.svg)](badges/coverage.svg)
[![uv](https://img.shields.io/badge/uv-package%20manager-green.svg)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/badge/ruff-linted-261230.svg)](https://github.com/astral-sh/ruff)

A YAML-defined world content engine for Evennia, and the game built on it.

Generated from the
[mcgov-python-template](https://github.com/ShaneMcGovern/probable-tribble) Copier
template, which supplies the parts that are tedious to assemble and easy to get
subtly wrong: a reproducible dev container, a locked `uv` environment, and a
pre-commit gate that runs identically on your machine and in CI, plus releases
driven by commit messages. `.copier-answers.yml` records the answers, so
`uvx copier update --trust` pulls in later improvements to the template without
losing your changes.

## Features

- **Reproducible dependencies** with
  [uv](https://github.com/astral-sh/uv) - a committed lockfile and no
  virtualenv to activate
- **Pre-configured tooling**: pytest with coverage, ruff linting and formatting,
  mypy in strict mode
- **One quality gate** shared by your machine and CI, so nothing passes locally
  and fails on push
- **GitHub Actions CI/CD** with automated testing and releases driven by commit
  messages
- **Zero host setup** - Docker Compose dev container, non-root user, persistent
  caches

## Installation

**Prerequisites**: [Docker](https://docs.docker.com/get-docker/),
[VS Code](https://code.visualstudio.com/), and the
[Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers).
No Python and no uv on the host.

First, check your git identity. `.devcontainer/.env` was created when this
project was generated, from the author details you gave then:

```bash
GIT_AUTHOR_NAME="Shane McGovern"
GIT_AUTHOR_EMAIL="shanemcgovern@protonmail.com"
```

Edit it if that isn't who should be committing here. The file is gitignored, so
it stays local to your checkout. `.devcontainer/.env.example` is the committed
copy and carries placeholders rather than these values — anyone else who clones
this repository copies it and fills in their own identity.

These values are passed into the container and applied by `entrypoint.sh`, so
commits made inside the container carry the right author. They must not be
empty: git reads them directly and they outrank `user.name`, so a blank value
fails every commit with `fatal: empty ident name`.

### Option 1: VS Code Dev Container (Recommended)

Open the folder in VS Code, then click **"Reopen in Container"** or use the
Command Palette (`Cmd/Ctrl+Shift+P`) → **"Dev Containers: Reopen in Container"**.

On first start the container syncs the environment (`uv sync`) and installs the
pre-commit hooks. Both are automatic.

### Option 2: Docker Compose

Run the container directly with Docker Compose:

```bash
# Build and start the container
docker compose -f .devcontainer/compose.yaml up -d --build

# Open a shell inside it
docker compose -f .devcontainer/compose.yaml exec app bash

# Stop the container
docker compose -f .devcontainer/compose.yaml down
```

`entrypoint.sh` applies your git identity, runs `uv sync`, and installs the
pre-commit hooks on every start. `devcontainer.json` is a thin wrapper over this
same compose file that adds editor settings and nothing else, so the two entry
points can't drift apart.

**Start the container before your first push.** A freshly generated project has
no `uv.lock`: that first `uv sync` writes it, using the interpreter already
inside the image. Generation deliberately does not build it, so that it cannot
depend on what Python your *host* happens to have. Both workflows install with
`uv sync --frozen`, so CI needs the lock committed — start the container, let it
sync, and commit the `uv.lock` it produces along with everything else.

Either way, **commit from inside the container**. The git hooks invoke `uv run`,
so they need the container's toolchain, and `git commit` from the host will try
to use a host Python and fail. The VS Code terminal already is a container
shell.

## Quick Start

Once the container is running:

```bash
# Run the tests, with coverage
uv run pytest

# Validate YAML world content
uv run mudification validate tests/fixtures/corpus/basic

# Run every hook, exactly as CI runs them
uv run pre-commit run --all-files
```

The `mudification` command is installed into the environment by `uv sync`.

The everyday commands for changing the project - linting, type checking, adding
a dependency, and the full hook list - are in
[CONTRIBUTING.md](CONTRIBUTING.md).

## CI and Releases

Two workflows, both in `.github/workflows/`.

**`validate.yml`** runs on PRs to `main` only. It is the gate: nothing reaches
`main` without a green run, so it deliberately does not re-run on the merge
itself.

1. `pre-commit` - every hook, across all files.
2. `test` - pytest.

**`release.yml`** runs on pushes to `main` with two jobs. `release` first
verifies that the pushed commit arrived through a PR whose Validate run was
green - the repository's plan has no required status checks, so this is what
enforces the gate - then hands off to python-semantic-release, which reads its
configuration from `pyproject.toml`. Releases are derived from commit messages,
so the type prefix decides what happens; [CONTRIBUTING.md](CONTRIBUTING.md) has
the vocabulary and which prefixes ship a release.

On a release, python-semantic-release bumps the version in `pyproject.toml`
(the only place it appears), inserts the new entry into `CHANGELOG.md` below its
`<!-- version list -->` marker, re-locks `uv.lock` so its recorded version
follows, tags, and publishes a GitHub Release.

Nothing is published to an index yet, but the package is installed into the
environment by `uv sync`. `build_command` runs `uv lock` so that `uv.lock`'s
recorded project version follows the bump PSR just wrote into `pyproject.toml`;
`assets` carries the regenerated lock into the release commit. Without that,
every release left the lock stale and the `uv-lock` hook failed on the next
push.

The `badge` job regenerates `badges/coverage.svg` from a fresh run of the suite
and commits it if it changed. Both jobs share a `concurrency` group, so they
can't race each other pushing to `main`.

## Updating from the Template

This project was generated from a Copier template, and `.copier-answers.yml`
records which version and which answers. To pull in later template improvements:

```bash
# Re-ask each question, prior answer as the default
uvx copier update --trust

# Reuse every prior answer, no prompts
uvx copier update --trust --defaults
```

**Commit your work first**: Copier refuses to update a dirty tree. It then
re-applies the template and merges the result with your changes, prompting where
they conflict.

`update` moves to the template's newest **tag**, so an untagged template change
is invisible to it. And `uvx` fetches whatever Copier version is current, so
pin it (`uvx copier@9.17.2`) when the update needs to be reproducible.

A few template releases restructure a generated project in ways `update` cannot
merge on its own, and jumping across one leaves you to reconcile the result by
hand. The template's
[UPGRADING.md](https://github.com/ShaneMcGovern/probable-tribble/blob/main/docs/UPGRADING.md)
lists those releases, what each one changed, and the order to step through them
in. Read it before updating across several versions at once.

## Layout

```text
.devcontainer/       Dockerfile, compose, entrypoint, VS Code wiring
.github/workflows/   validate.yml (gate) and release.yml (release + badge)
badges/              coverage.svg, regenerated by CI on main
src/evennia_mudification/  the engine package
tests/               the test suite
```

## Documentation

- **[uv Documentation](https://docs.astral.sh/uv/)** - Package manager and
  lockfile reference
- **[Ruff Documentation](https://docs.astral.sh/ruff/)** - Linter and formatter
  rules
- **[mypy Documentation](https://mypy.readthedocs.io/)** - Static type checker
  configuration
- **[pytest Documentation](https://docs.pytest.org/)** - Testing framework guide
- **[VS Code Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers)** -
  Container development guide
- **[mcgov-python-template](https://github.com/ShaneMcGovern/probable-tribble)** -
  The template this project came from

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the change workflow: the quality
gate, commit message rules, dependency management, tests, and types.

## License

MIT License - see the [LICENSE](LICENSE) file for details.

© 2026 Shane McGovern
