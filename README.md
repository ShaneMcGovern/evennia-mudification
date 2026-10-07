# mudification

Contribution by Shane McGovern, 2026

A YAML-defined world content engine for Evennia. Define rooms, exits, objects and prototype templates in YAML files, validate them offline before anything runs, and apply them to a running game with an explicit command. The fields your content declares belong to the content; everything else, including whatever a builder changes in game, survives every apply. This is version 0.3.0, with a test suite whose coverage floor is enforced on CI, and the test and coverage badges below. The author guide is at [docs/authoring-guide.md](docs/authoring-guide.md).

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.13.15](https://img.shields.io/badge/python-3.13.15-blue.svg)](https://www.python.org/downloads/)
[![Validate](https://github.com/ShaneMcGovern/evennia-mudification/actions/workflows/validate.yml/badge.svg?event=pull_request)](https://github.com/ShaneMcGovern/evennia-mudification/actions/workflows/validate.yml)
[![Coverage](badges/coverage.svg)](badges/coverage.svg)
[![uv](https://img.shields.io/badge/uv-package%20manager-green.svg)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/badge/ruff-linted-261230.svg)](https://github.com/astral-sh/ruff)

## Installation

Requires an Evennia 6.1 or later game running Python 3.13 or later. Install into the same environment as the game.

From the repository at tag `v0.3.0`, with [uv](https://github.com/astral-sh/uv):

```bash
uv add "evennia-mudification @ git+https://github.com/ShaneMcGovern/evennia-mudification.git@v0.3.0"
```

With pip:

```bash
pip install "evennia-mudification @ git+https://github.com/ShaneMcGovern/evennia-mudification.git@v0.3.0"
```

The package is not published to an index yet; install it from the repository above.

Then make three changes in the game directory.

1. In `server/conf/settings.py`, name your content root:

   ```python
   MUDIFICATION_CONTENT_PATH = "path/to/content"
   MUDIFICATION_FALLBACK_ROOM = "#dbref"  # optional
   ```

2. In `server/conf/at_server_startstop.py`, add the start check:

   ```python
   def at_server_start():
       from evennia_mudification import validate_on_start
       validate_on_start()
   ```

   Validation runs at every start, reports to the log and to connected superusers and admins, and never mutates the world.

3. In `server/conf/commands/default_cmdsets.py`, add the command beside the default commands:

   ```python
   from evennia import default_cmds
   from evennia_mudification.commands import CmdMudification


   class CharacterCmdSet(default_cmds.CharacterCmdSet):
       def at_cmdset_creation(self):
           super().at_cmdset_creation()
           self.add(CmdMudification)
   ```

   The command needs `Developer` permission.

## Usage

1. Write your world under the content root: rooms, exits, objects and prototype templates in YAML.
2. Validate it offline, in CI or in any terminal: `mudification validate content`.
3. See what would change in the running game: `mudification plan`.
4. Apply the plan explicitly: `mudification apply confirm`.
5. Retire what content dropped: `mudification prune`, then `mudification prune confirm`.

The [authoring guide](docs/authoring-guide.md) has the content model and every field.

## Examples

Save this world as `content/world.yaml`. It nests objects, counts rats, reverses an exit and uses a prototype template:

```yaml
schema_version: 1
zone: keep
entities:
  - id: hall
    kind: room
    key: The Great Hall
    contents:
      - id: chest
        kind: object
        key: a heavy chest
        attrs:
          desc: Iron-bound oak.
        contents:
          - id: coin
            kind: object
            key: a gold coin
  - id: cellar
    kind: room
    key: the cellar
  - id: hall-cellar
    kind: exit
    key: cellar stairs
    location: "@hall"
    destination: "@cellar"
    reverse: true
  - id: rats
    kind: object
    key: a sewer rat
    count: 3
    attrs:
      desc: It squeaks.
  - id: goblin_tpl
    kind: prototype
    key: goblin template
    typeclass: evennia.objects.objects.DefaultObject
    attrs:
      hp: 5
  - id: goblin_guard
    kind: object
    key: the goblin guard
    prototype: "@goblin_tpl"
    location: "@hall"
```

Run the lifecycle against it:

```text
> mudification validate
11 entities valid.
> mudification plan
create hall
create cellar
create hall-cellar
create goblin_guard
create chest
create coin
create rats#1
create rats#2
create rats#3
create hall-cellar:reverse
> mudification apply confirm
create hall: ok
create cellar: ok
create hall-cellar: ok
create hall-cellar:reverse: ok
create goblin_guard: ok
create chest: ok
create coin: ok
create rats#1: ok
create rats#2: ok
create rats#3: ok
> mudification prune confirm
evacuated 0, destroyed 0
```

Apply and prune run on the server's own thread on the stock sqlite install, and off the reactor thread on postgres (the immediate answer is then `applying off-thread; results will follow.`). While one apply or prune is in flight, the next confirmation is refused with `already running`.

Prune finds nothing here because the content still declares every entity. Drop one from the YAML and `mudification prune` lists it as a retirement before `prune confirm` executes it.

## Content model

- **Rooms** are places. Child objects go under `contents`.
- **Exits** link two rooms and can synthesize a return exit with `reverse`.
- **Objects** are things; `count: N` expands one declaration into instances `#1` to `#N`.
- **Nested contents** put objects inside rooms or other objects, as deep as you need.
- **Prototypes** are templates, declared with `kind: prototype` and inherited with `prototype: "@id"`.
- **Undeclared state survives**: only the fields your content declares are owned and updated, so builder edits, scripts and extra attributes stay.

Content flows one way, from YAML into the game. There is no export back to YAML yet, no remote content fetching, and nothing is applied automatically at server start.

The [authoring guide](docs/authoring-guide.md) documents every field, the finding codes and troubleshooting.

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `MUDIFICATION_CONTENT_PATH` | none in game; the CLI reads `$MUDIFICATION_CONTENT_PATH`, then falls back to `content` in the working directory | the content root the in-game command and the start check read |
| `MUDIFICATION_FALLBACK_ROOM` | Evennia's `DEFAULT_HOME` | the `#dbref` of the room that receives occupants a retiring room or object cannot send home |

## Commands

In game, the package ships one command, `mudification`:

| Command | What it prints |
| --- | --- |
| `mudification validate` | reloads content from disk; `<n> entities valid.` or the errors and a note that nothing was applied |
| `mudification plan` | the diff: `create <id>`, `update <id>: <fields>`, `retire <id> (reported only)`, or `no changes` |
| `mudification apply` | the same plan; when it has creates or updates, a confirmation hint. Applies nothing |
| `mudification apply confirm` | executes the plan and reports `action <id>: ok` or a failure per entity |
| `mudification prune` | the `retire` and `evacuate` lines; when it has retirements, a confirmation hint. A refusal instead, with no hint |
| `mudification prune confirm` | executes the evacuations and destructions and reports the counts |
| `mudification status` | the last validation summary, managed entities in the database, the last applied count, retirements and source bundles |

Its alias is `evennia_mudification`, and with no argument it runs `status`.

The CLI covers validation in CI, or in a pre-commit hook you add yourself:

- `mudification validate [path] [--json]`: validate a content root. Prints one line per finding and a summary line; exit code 0 when clean, 1 when there are errors. `--json` emits the findings as JSON.
- `mudification schema [--write PATH]`: print the JSON Schema for bundles, or write it to PATH for editors, defaulting to `schema/mudification.schema.json`.

## Known limitations

- Dropping a declaration never removes a live value; removal happens only through retirement, which prune executes.
- A template removed from content stays spawnable until the next server restart.

## Development

Clone the repository and open the dev container; [CONTRIBUTING.md](CONTRIBUTING.md) has the prerequisites and both start options. Run the suite with `uv run pytest` and every hook with `uv run pre-commit run --all-files`. Releases are automated from Conventional Commits.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the change workflow: the quality gate, commit message rules, dependency management, tests, and types.

## License

MIT License - see the [LICENSE](LICENSE) file for details.

© 2026 Shane McGovern
