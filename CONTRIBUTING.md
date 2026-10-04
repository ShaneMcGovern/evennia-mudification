# Contributing

## Setup

[README.md](README.md) has the prerequisites, the git identity `.devcontainer/.env`
supplies, and both ways to start the container. Do that first; everything below
assumes you are inside it.

### Why everything runs in the container

The container is the only environment whose Python and uv versions are pinned
and reproducible. Running tools against a host Python will eventually disagree
with CI. Every command in this document assumes you are inside the container.

This applies to `git commit` as well. The installed hooks invoke `uv run`, so
committing from a host shell fails on the host Python. Commit from a container
shell; the VS Code terminal already is one.

## Making a change

```text
edit -> git commit -> hooks run -> push -> CI -> merge to main -> release
```

1. Branch from `main`:

   ```bash
   git checkout -b feature/short-description
   ```

2. Make the change, with tests.

3. Run the gate:

   ```bash
   uv run pre-commit run --all-files
   uv run pytest
   ```

4. Commit. The hooks run automatically, and the commit-msg hook rejects any
   message that is not a Conventional Commit.

5. Push and open a PR against `main`.

Everyday commands:

```bash
# Tests, with coverage
uv run pytest

# Lint, fixing what can be fixed
uv run ruff check --fix .

# Format
uv run ruff format .

# Type check
uv run mypy

# Every hook, exactly as CI runs them
uv run pre-commit run --all-files
```

`pre-commit run --all-files` covers CI's `pre-commit` job but not its `test`
job, because pytest is not a hook. Run both before pushing. `uv run` syncs the
environment before running, so there's no virtualenv to activate.

## Quality gate

`.pre-commit-config.yaml` is the single definition of "correct", used by your
local hooks and by CI.

One stage is local-only, and deliberately so. CI runs
`pre-commit run --all-files`, which runs the `pre-commit` stage; the
`commit-msg` stage needs a commit message to check and there is no such thing in
a `--all-files` run. `conventional-pre-commit` therefore guards your commits and
not the branch, so a message written with `--no-verify`, or on the web, reaches
`main` unchecked.

| Hook | Stage | What it does |
| --- | --- | --- |
| Hygiene hooks | pre-commit | Whitespace, EOF, merge markers, large files, private keys, LF endings |
| `check-yaml`, `check-json`, `check-toml` | pre-commit | Parse validity |
| `prettier` | pre-commit | Formats YAML and JSON |
| `markdownlint-fix` | pre-commit | Formats and lints Markdown |
| `shellcheck` | pre-commit | Lints shell scripts |
| `ruff-check`, `ruff-format` | pre-commit | Lints and formats Python |
| `mypy` | pre-commit | Type checks `src/` and `tests/` |
| `uv-lock` | pre-commit | Fails if `uv.lock` has drifted |
| `conventional-pre-commit` | commit-msg | Rejects non-Conventional commit messages |

Several of these are deliberately configured against the obvious default:

- **`ruff` and `mypy` run as local hooks** (`uv run ruff`, `uv run mypy`) rather
  than through mirror repositories. For mypy this is necessary: a mirrored hook
  runs in an isolated environment that cannot see project dependencies, so it
  reports false import errors as soon as there are any. For ruff it means there
  is one version, declared in `pyproject.toml` and locked in `uv.lock`, so
  `uv run ruff` and the CI hook cannot drift apart and enforce different rules.
- **`prettier` is not given TOML.** It can't parse TOML without a plugin.
- **`check-json` and `prettier` both skip `devcontainer.json`.** It's JSONC:
  the comments in it are valid there and are a parse error to both tools.
- **`markdownlint` skips `CHANGELOG.md`.** python-semantic-release generates it
  and emits two blank lines between releases, which trips MD012. Since the
  release commit carries `[skip ci]`, that would land unchecked and fail the
  *next* push, leaving CI red after every release.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/), enforced by the
`conventional-pre-commit` hook. The format feeds the release pipeline:
python-semantic-release derives the next version from it, and a message it
can't parse silently produces no release.

```text
<type>: <description>
```

| Type | Meaning | Releases? |
| --- | --- | --- |
| `feat` | New functionality | Minor |
| `fix` | Bug fix | Patch |
| `perf` | Performance improvement | **Patch** |
| `docs` | Documentation only | No |
| `refactor` | Restructuring without behaviour change | No |
| `test` | Tests only | No |
| `build` | Build system, dependencies, container | No |
| `ci` | CI configuration | No |
| `chore` | Everything else | No |
| `style` | Formatting only | No |

Breaking changes take a `!` after the type (`feat!: ...`) or a
`BREAKING CHANGE:` footer, and produce a major bump.

`perf` is the one to watch: it reads like housekeeping but ships a patch
release, because PSR's conventional parser sets `patch_tags = ("fix", "perf")`.
`revert` is accepted by the commit-msg hook but is not one of PSR's allowed
tags, so it produces no release.

Examples:

```text
feat: add --json output flag
fix: handle empty input without raising
docs: document the release pipeline
```

## Pull requests

PRs are squash-merged, so **the PR title becomes the commit message on `main`** —
it must be a valid Conventional Commit. The commit-msg hook can't check a PR
title, so this one is on you.

`validate.yml` runs on the branch push and again on the PR. It also runs on
`main` after the merge, because a squashed commit is a commit no CI run has
seen before.

## Dependencies

```bash
uv add httpx                      # runtime
uv add --group dev pytest-mock    # development only
uv remove httpx
```

Always commit `uv.lock`. CI installs with `--frozen` and fails if the lock has
drifted; the `uv-lock` hook catches it locally first.

### Updating pinned tools

Separate mechanisms, because no single one covers everything:

| What | How |
| --- | --- |
| Python dependencies | Dependabot, weekly (`uv` ecosystem) |
| GitHub Actions | Dependabot, weekly (`github-actions` ecosystem) |
| Base and uv images | Dependabot, weekly (`docker` ecosystem, `/.devcontainer`) |
| pre-commit hooks | Manual: `uv run pre-commit autoupdate` |
| python-semantic-release | Manual: the version in `.github/workflows/release.yml` |

Dependabot has no pre-commit ecosystem, which is why the pre-commit row is
manual. Run it periodically and follow with `uv run pre-commit run --all-files`,
since a new hook revision often surfaces new findings.

The last row is manual for a different reason: `release.yml` invokes PSR through
`uvx` with an explicit version rather than using its GitHub Action, so no
Dependabot ecosystem can see it. The workflow comment beside that line records
why and the condition for dropping the pin.

ruff and mypy are **not** pinned by hand. They're declared in
`pyproject.toml`, locked in `uv.lock`, and called by local hooks, so
Dependabot's `uv` ecosystem updates them and there is only ever one version of
each.

## Tests

pytest, with coverage measured against `src/`.

```bash
uv run pytest                         # everything, with coverage
uv run pytest tests/test_smoke.py -v  # one file
uv run pytest -k runnable             # by name
```

Coverage has no `omit` or `exclude_lines` rules. If you find yourself adding
one, check first whether the code it hides is actually needed.

`tests/test_smoke.py` covers the entry point three ways, and the third earns its
place. Calling `main()` and `runpy.run_module` both run inside pytest, so they
inherit the `pythonpath` it applied and would pass even if a real invocation
couldn't find the module. `test_entry_point_works_as_a_real_command` spawns a
fresh interpreter, so only it can fail that way.

That matters because `package = false` means uv never installs the project, so
`src/` reaches `sys.path` only through the configuration the README describes.

## Types

mypy runs in `strict` mode over `src/` and `tests/`, including test functions.
New code needs annotations:

```python
def render(rows: list[str], *, indent: int = 0) -> str: ...
```

```bash
uv run mypy
```

## Releasing

There's nothing to do. Merging a `feat:`, `fix:`, or `perf:` commit to `main`
triggers `release.yml`, and [README.md](README.md) describes what that pipeline
does.

Never edit `CHANGELOG.md` by hand or bump a version manually:
python-semantic-release owns both, and a manual edit will be overwritten or will
desynchronise the two version locations.
