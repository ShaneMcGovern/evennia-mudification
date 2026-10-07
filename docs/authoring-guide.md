# Authoring world content

Define your world as YAML files, validate them offline before anything runs, and apply them to a live game with an explicit command. The engine owns only the fields your content declares, so in-game state it did not declare, including builder edits, survives every apply.

## Prerequisites

- An Evennia 6.1 game or later, running on Python 3.13 or later.
- The package installed into the game's environment. The README's [Installation](../README.md#installation) section has the install command.
- A content root directory for your YAML, named in `MUDIFICATION_CONTENT_PATH` (see Settings).

## A first bundle

Keep content in a directory tree under the content root. This guide uses `content/` inside the game directory, with one file:

```text
game/
  content/
    village.yaml
```

Write `content/village.yaml`:

```yaml
schema_version: 1
zone: village
entities:
  - id: square
    kind: room
    key: The village square
    desc: |
      A well-worn square.
  - id: inn
    kind: room
    key: The Wayfarer's Inn
  - id: square-inn
    kind: exit
    key: inn door
    aliases: [in]
    location: "@square"
    destination: "@inn"
  - id: signpost
    kind: object
    key: a wooden signpost
    location: "@square"
    locks:
      get: "false()"
    permissions:
      - Builders
    attrs:
      desc: Points in four directions.
```

From the game directory, validate the tree:

```bash
mudification validate content
```

```text
4 entities, 0 errors, 0 warnings
```

The loader reads every `*.yaml` and `*.yml` file under the path in sorted order, so a tree of subdirectories works the same way. A root holding none of either is a `no-bundles-found` error, and a file that parses to nothing is an `empty-bundle` error, so a renamed extension or a blanked file cannot silently drop content.

## Bundles

Each YAML file is one bundle with three top-level fields:

- `schema_version` (required): the format version. Version `1` is the only supported value.
- `zone` (optional): a label for your own organisation. The engine accepts it and otherwise ignores it, so it has no effect in 0.3.0.
- `entities` (required): the list of entity declarations.

A minimal bundle:

```yaml
schema_version: 1
zone: village
entities:
  - id: square
    kind: room
    key: The village square
```

More rules:

- YAML is parsed with `yaml.safe_load` only. Custom tags and Python-specific forms are not accepted.
- Unknown fields are rejected at every level. A typo in a field name fails validation instead of being ignored.
- An id matches `[a-z0-9][a-z0-9_-]*` and must be unique across the whole content root, not just within its file.
- Changing an id is a retire plus create: the new id is planned as a create, and the live object still carrying the old id is reported as a retirement. Changing a `key` is an ordinary update.

## Entities

Every entity declares a `kind` and the common fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `kind` | yes | `room`, `exit`, `object` or `prototype` |
| `id` | yes | the entity's stable identity, and the name other entities reference |
| `key` | yes | the display name; must not be blank |
| `typeclass` | no | dotted path of the typeclass to spawn. When omitted, the engine uses Evennia's base typeclass for the kind; for an object with a `prototype`, the template's typeclass applies |
| `aliases` | no | list of alternative names |
| `attrs` | no | mapping of attribute name to value |
| `tags` | no | mapping of tag key to tag category |
| `locks` | no | mapping of lock name to lockstring |
| `permissions` | no | list of permission names |
| `desc` | no | shorthand for `attrs.desc`. If both are declared, `attrs.desc` wins |

References are strings of the form `"@id"`, and the id must name a declared entity. They are valid on four fields:

- `location`: where the entity stands. Objects and exits.
- `destination`: where an exit leads. Exits only, and required there.
- `home`: where an object is sent when it goes home. Objects only.
- `prototype`: the template an object inherits from. Objects only.

## Rooms, exits and objects

### Rooms

A `kind: room` entity is a place. Rooms may declare `contents` (see Nesting) and nothing besides the common fields.

### Exits

A `kind: exit` entity is a link. `location` and `destination` are both required, and both must name rooms. Anything else is a `location-not-room` or `destination-not-room` error.

`reverse` is optional and has two forms:

- `reverse: true` synthesizes a return exit with the id `<id>:reverse`, swapping location and destination. By default its key is the key of the room it leads to, which is the room the original exit came from, and it has no aliases.
- `reverse: {key: ..., aliases: [...]}` synthesizes the same exit with the key and aliases you choose. Either field may be omitted, and the default applies for whichever is missing.

### Objects

A `kind: object` entity is a thing. `location` may name a room or another object, and `home` names the object's home, again a room or another object. An exit or a template is never a valid target for either: an exit is a link, and a template is never a live object. Placement must not form a cycle: an object cannot sit inside itself, directly or through a chain, and one that does is a `location-cycle` error. Objects may also declare `count` (see Counts), `prototype` (see Prototypes) and `contents` (see Nesting).

Here is one bundle using all three kinds:

```yaml
schema_version: 1
entities:
  - id: inn-yard
    kind: room
    key: the inn yard
  - id: inn
    kind: room
    key: The Wayfarer's Inn
  - id: bench
    kind: object
    key: a long bench
    location: "@inn-yard"
    home: "@inn"
  - id: inn-door
    kind: exit
    key: door
    aliases: [in]
    location: "@inn-yard"
    destination: "@inn"
    reverse: true
  - id: inn-arch
    kind: exit
    key: side arch
    location: "@inn-yard"
    destination: "@inn"
    reverse:
      key: back to the yard
      aliases: [out]
```

Validating it reports `7 entities, 0 errors, 0 warnings`: the five declared entities plus the two synthesized reverse exits.

## Counts

`count: N` on an object expands it into N instances with the ids `<id>#1` through `<id>#N`.

```yaml
schema_version: 1
entities:
  - id: cellar
    kind: room
    key: the cellar
  - id: rats
    kind: object
    key: a sewer rat
    location: "@cellar"
    count: 3
```

Validating that bundle reports `4 entities, 0 errors, 0 warnings`: the cellar and the three rats.

Each instance is an entity in its own right. Plans create, update and retire instances individually, so lowering `count: 3` to `count: 2` retires `rats#3` and leaves the other two alone.

After expansion the base id no longer exists. A reference to `"@rats"` is therefore a `dangling-ref` error, and the generated instance ids contain `#`, which the reference grammar does not allow, so an instance cannot be referenced either. If another entity must sit inside a counted object, or point at one, declare that object without `count` instead.

A counted entity must not declare `contents`. That is the `count-with-contents` error; declare the object without `count` if it needs children.

`count` is capped at 10000 instances; anything larger is a schema error, so a mistyped digit fails validation instead of exhausting the machine.

## Nesting

Rooms and objects may declare `contents`, a list of child entities. Children:

- must be objects (the schema rejects anything else),
- need their own ids,
- must not declare a `location` (`nested-location`), because the compiler injects `location: "@parent"`.

Nesting may go as deep as you like: a chest inside a hall, a coin inside the chest.

```yaml
schema_version: 1
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
```

Validating that bundle reports `3 entities, 0 errors, 0 warnings`: the hall, the chest and the coin. A child id that repeats an existing id anywhere in the content root is a `duplicate-id` error.

## Prototypes

A `kind: prototype` entity is a template, not a world object. It declares the common fields, with none of the placement fields (`location`, `home`, `count`, `prototype` or `contents`). An object inherits from it with `prototype: "@id"`.

```yaml
schema_version: 1
entities:
  - id: hall
    kind: room
    key: The Great Hall
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

Validating that bundle reports `3 entities, 0 errors, 0 warnings`. The goblin guard spawns with `hp: 5` from the template and its own key and location. A typeclass declared on the object wins over the template's; when the object declares none, the template's applies.

In the game process, the server start check and a confirmed `apply` or `prune` register every template with Evennia as a read-only module prototype. The inspection commands (`validate`, `plan`, `status`) never touch the prototype namespace, and the offline CLI never registers. In game, `spawn goblin_tpl` works, and the template appears in OLC's prototype list. Templates are not planned or applied as objects themselves.

A template id is also its prototype key. A key the game already ships through `settings.PROTOTYPE_MODULES` is never overwritten: validation reports `prototype-key-taken` and nothing is applied, so rename the content id. A template removed from the content is deregistered by the next confirmed apply or prune, or by a server restart.

A template's fields count as declared for its children. Editing a template updates existing children on the next apply, and repointing an object's `prototype:` reference applies the new template's fields, with the plan showing the affected fields like any other declared change. A field the object declares itself still wins over the template's.

## What apply owns

Every object the engine creates carries two identity tags: the entity id in the `mudification` category and the source file in `mudification_source`. Planning, ref resolution and retirement detection treat an object as managed only when both are present, so a hand-added tag changes nothing by itself. Removing either tag orphans the object: the engine stops seeing it, and the next plan creates a replacement for its id.

When two live objects claim one id (a crash mid-apply, or a manual copy), `plan` reports `duplicate <id>: <n> live objects`; an update touches the first copy only, and prune retires every copy in one run.

The declared fields are the content's to own: key, typeclass, aliases, attrs, tags, locks, permissions and the references. Everything else on a live object survives every apply. Builder edits, scripts attached in game, extra descriptions, extra aliases and extra locks are all left alone. An empty list or mapping declaration (aliases, attrs, tags, locks, permissions) is omitted rather than sent as empty, so it never clears live state. The exception is `desc`: an explicit `desc: ""` is sent, and clears the live description on update.

Dropping a declaration never removes a live value. Delete `aliases: [a]` from the content and `a` stays on the object; the plan reports no change, because under additive-only semantics there is nothing for it to change. To clear a value, remove it in game, or use the empty spelling the field supports, such as `desc: ""`. Removal happens only through retirement: dropping an entity's id, or re-declaring it as a template, reports the live object as a retirement for prune to destroy. The declared fields are additive, and the content never silently deletes what it no longer mentions.

Re-applying unchanged content changes nothing, so apply is safe to run again at any time. When content drops an entity, `plan` and `prune` report it as a retirement. An id that changes kind to `kind: prototype` retires its live object the same way, because it is no longer a declared world object. Apply never deletes anything.

## Pruning

`mudification prune` lists what would be retired and where occupants would move. `mudification prune confirm` executes it. Nothing is ever pruned by apply or by server start.

The rules:

- Occupants of a retiring room move to their home when it is live and not itself retiring, otherwise to the fallback room.
- Contents of a retiring object move to the fallback room.
- Exits are never evacuated: a retiring room's delete destroys its exits, so they cannot be stranded in a home room.
- Occupants that are themselves retiring are skipped, because this run destroys them anyway.
- If a surviving occupant needs the fallback and no usable fallback resolves, or the fallback is itself retiring, unresolvable, or not a room, the plan refuses with `fallback-missing` and nothing is destroyed.
- Every evacuation runs before any destruction. If an evacuation fails, destruction is skipped entirely, so a container is never deleted while an occupant is stranded.

## Validation and findings

Validation runs in four layers:

1. Structural: the file parses as YAML, matches the bundle schema, and passes the compile rules for ids, nesting and counts. Reading the content root and its files is here too.
2. Semantic: references resolve to entities of the right kind, tags avoid the reserved categories, and, when Evennia is importable, protfunc names, lockstrings, typeclass paths and template key collisions are checked against Evennia itself.
3. Plan-time: the diff against the live database, retirements, and the prune fallback check.
4. Runtime: per-entity failures while apply or prune runs. Failures are collected, the run continues, and the summary reports each failed entity.

Apply refuses to run while any structural or semantic error stands; the command prints the errors and applies nothing. Plan-time results are shown for a human decision. Warnings never stop a run.

The finding codes:

| Code | Severity | What triggers it |
| --- | --- | --- |
| `yaml-parse` | error | A file is not valid YAML. |
| `schema` | error | A bundle does not match the schema: unknown field, wrong type, missing required field, bad id, blank key, or a `schema_version` other than 1. |
| `duplicate-id` | error | An id is declared twice, in one bundle or across the content root, including a nested child that repeats an existing id; a nested duplicate's discarded descendants are named in the finding. |
| `nested-location` | error | A `contents` child declares its own `location`. |
| `count-with-contents` | error | An entity declares both `count` and `contents`. |
| `content-root-missing` | error | The content root does not exist or is not a directory. |
| `no-bundles-found` | error | The content root holds no `*.yaml` or `*.yml` files. |
| `empty-bundle` | error | A bundle file parses to nothing, for example an empty or comment-only file. |
| `load-error` | error | A bundle could not be read or loaded, for example an unreadable file or invalid UTF-8. |
| `semantic-checks-skipped` | warning | The CLI could not import Evennia, so the Evennia-dependent checks did not run. |
| `dangling-ref` | error | A `@id` reference matches no declared entity. |
| `location-not-room` | error | An exit's `location` reference points at something that is not a room. |
| `destination-not-room` | error | An exit's `destination` reference points at something that is not a room. |
| `location-cycle` | error | Object `location` refs form a placement cycle, including an object placed inside itself. |
| `location-not-room-or-object` | error | An object's `location` reference points at an exit or a template. |
| `home-not-room-or-object` | error | An object's `home` reference points at an exit or a template. |
| `prototype-not-found` | error | A `prototype` reference matches no declared entity. |
| `prototype-not-a-template` | error | A `prototype` reference points at an entity that is not `kind: prototype`. |
| `prototype-key-taken` | error | A template id collides with a prototype key the game already ships (`settings.PROTOTYPE_MODULES`). |
| `reserved-tag-category` | error | A tag claims a category the engine reserves, `mudification` or `mudification_source`. |
| `unknown-protfunc` | error | A `$name(...)` reference in a key, desc or attribute is not a registered Evennia protfunc. |
| `invalid-lock` | error | Evennia rejects a declared lockstring. |
| `typeclass-unresolved` | error in game, warning from the CLI | A typeclass path cannot be imported in this environment, resolved the way the spawner does through `settings.TYPECLASS_PATHS`. The CLI warns rather than refusing because it runs outside the game and may not have the game's typeclass modules on its path. |
| `fallback-missing` | error | A prune plan needs the fallback room for a surviving occupant and no usable fallback resolves. |

## Settings

Put these in `server/conf/settings.py`:

```python
MUDIFICATION_CONTENT_PATH = "/home/you/game/content"
MUDIFICATION_FALLBACK_ROOM = "#2"
```

- `MUDIFICATION_CONTENT_PATH`: the content root. The in-game command and the server start check read it from Django settings. The CLI also reads it from the environment, where it is the default for `validate` when no path argument is given; with neither, the CLI falls back to `content` in the current directory.
- `MUDIFICATION_FALLBACK_ROOM`: optional `#dbref` of the room used when a retiring room or object has an occupant that cannot go home. It defaults to Evennia's `DEFAULT_HOME`.

## Commands

In game, the package ships one command, `mudification`. Add it to the game's default cmdset the way the README's Installation describes; the table below lists its subcommands:

| Command | What it prints |
| --- | --- |
| `mudification validate` | reloads content from disk; `<n> entities valid.` or the errors and a note that nothing was applied |
| `mudification plan` | the diff: `create <id>`, `update <id>: <fields>`, `retire <id> (reported only)`, or `no changes` |
| `mudification apply` | the same plan; when it has creates or updates, a confirmation hint. Applies nothing |
| `mudification apply confirm` | executes the plan and reports `action <id>: ok` or a failure per entity |
| `mudification prune` | the `retire` and `evacuate` lines; when it has retirements, a confirmation hint. A refusal instead, with no hint |
| `mudification prune confirm` | executes the evacuations and destructions and reports the counts |
| `mudification status` | the last validation summary, managed entities in the database, the last applied count, retirements and source bundles |

The command needs `Developer` permission. Its alias is `evennia_mudification`, and with no argument it runs `status`.

The CLI covers validation in CI, or in a pre-commit hook you add yourself:

- `mudification validate [path] [--json]`: validate a content root. Prints one line per finding and a summary line; exit code 0 when clean, 1 when there are errors. `--json` emits the findings as JSON. When Evennia is not importable, the protfunc, lockstring and typeclass checks cannot run; the run says so with a `semantic-checks-skipped` warning rather than reporting a clean bill of health.
- `mudification schema [--write PATH]`: print the JSON Schema for bundles, or write it to PATH for editors, defaulting to `schema/mudification.schema.json`.
- `mudification --version`: print the installed version.

## The full example

This is the lifecycle example, one world that uses nesting, a count, a reverse exit and a template. Save it as `content/world.yaml`:

```text
game/
  content/
    world.yaml
```

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

Validate it offline:

```bash
mudification validate content
```

```text
11 entities, 0 errors, 0 warnings
```

Then, in game as a Developer:

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
```

On the stock sqlite install, apply and prune run on the server's own thread, as above. On postgres they run off the reactor thread instead, so the immediate answer is `applying off-thread; results will follow.` and the report arrives when the run finishes. While one run is in flight, a second `apply confirm` or `prune confirm` is refused with `an apply or prune is already running; wait for it to finish.`; the slot frees when the run reports, pass or fail.

Now edit `content/world.yaml` so the rats entry declares `count: 2`, and run again:

```text
> mudification plan
retire rats#3 (reported only)
> mudification prune
retire rats#3
run 'mudification prune confirm' to execute these changes.
> mudification prune confirm
destroy rats#3: ok
evacuated 0, destroyed 1
```

The hall, cellar and their contents were untouched, and the surviving rats were never updated, because none of their declared fields changed.

## Troubleshooting

### A reference does not resolve

The run fails with `dangling-ref: location ref '@rats' does not match any declared entity`. `destination` and `home` references report the same code with their own field name. A `prototype` reference that matches no declared entity is `prototype-not-found`, and one that points at an entity which is not `kind: prototype` is `prototype-not-a-template`. The name after `@` must match a declared id exactly, and the bundle declaring that id must sit under the same content root.

### An id is rejected

`schema: entities.0.room.id: String should match pattern '^[a-z0-9][a-z0-9_-]*$'`. Ids are lowercase and start with a letter or digit; they may then contain letters, digits, underscores and hyphens. Use `key` for a display name with spaces or capitals.

### A reference to a counted id fails

`count` replaces the base id with the instances `<id>#1` to `<id>#N`, so nothing named by the base id exists any more and a reference to it is a `dangling-ref`. The instance ids contain `#`, which the reference grammar does not allow, so they cannot be referenced either. If something must hold or target a counted object, declare that object without `count`.

### An exit destination is not a room

`destination-not-room: destination '@inn-sign' is not a room`, and a bad `location` reports `location-not-room` instead. Both ends of an exit must be `kind: room` entities. Point the exit at a room rather than at an object, a template or another exit.

### The content root is missing

`content-root-missing: content root '<path>' does not exist or is not a directory`. Check the spelling, that the path is a directory and not a file, and the working directory the command runs from: with no path argument the CLI falls back to `$MUDIFICATION_CONTENT_PATH`, then to `content` in the current directory.
