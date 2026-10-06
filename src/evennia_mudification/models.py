"""Pydantic models for mudification content bundles."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Expansion of a larger count already costs seconds and hundreds of megabytes,
# and every downstream pass multiplies it; a typo must fail fast instead.
MAX_COUNT = 10000

Id = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$")]
Ref = Annotated[str, StringConstraints(pattern=r"^@[a-z0-9][a-z0-9_-]*$")]
# A key may not be blank: Evennia would fall back to a generated name like #1.
Key = Annotated[str, StringConstraints(min_length=1, pattern=r".*\S.*")]


class EntityBase(BaseModel):
    """Fields every declared entity shares."""

    model_config = ConfigDict(extra="forbid")

    id: Id
    key: Key
    typeclass: str | None = None
    aliases: list[str] = Field(default_factory=list)
    attrs: dict[str, Any] = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)
    locks: dict[str, str] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)
    desc: str | None = None


class ReverseOverride(BaseModel):
    """Overrides for a synthesized reverse exit."""

    model_config = ConfigDict(extra="forbid")

    key: str | None = None
    aliases: list[str] = Field(default_factory=list)


class RoomEntity(EntityBase):
    """A room."""

    kind: Literal["room"]
    contents: list[ObjectEntity] = Field(default_factory=list)


class ExitEntity(EntityBase):
    """An exit between two rooms."""

    kind: Literal["exit"]
    location: Ref
    destination: Ref
    reverse: bool | ReverseOverride | None = None


class ObjectEntity(EntityBase):
    """A plain object; `location` may be a room or another object."""

    kind: Literal["object"]
    location: Ref | None = None
    home: Ref | None = None
    count: int | None = Field(default=None, ge=1, le=MAX_COUNT)
    prototype: Ref | None = None
    contents: list[ObjectEntity] = Field(default_factory=list)


class PrototypeEntity(EntityBase):
    """A reusable template other entities reference with ``prototype``."""

    kind: Literal["prototype"]


Entity = Annotated[
    RoomEntity | ExitEntity | ObjectEntity | PrototypeEntity,
    Field(discriminator="kind"),
]


class Bundle(BaseModel):
    """One YAML file's worth of content."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    zone: str | None = Field(
        default=None,
        description=(
            "A free-form label for your own organisation; the engine accepts "
            "it and otherwise ignores it."
        ),
    )
    entities: list[Entity]


def ref_target(ref: str) -> str:
    """Return the entity id a `@ref` points at."""
    return ref[1:]


Bundle.model_rebuild()
