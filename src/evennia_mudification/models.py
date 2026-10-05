"""Pydantic models for mudification content bundles."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SUPPORTED_SCHEMA_VERSIONS = (1,)

Id = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$")]
Ref = Annotated[str, StringConstraints(pattern=r"^@[a-z0-9][a-z0-9_-]*$")]


class EntityBase(BaseModel):
    """Fields every declared entity shares."""

    model_config = ConfigDict(extra="forbid")

    id: Id
    key: str
    typeclass: str | None = None
    aliases: list[str] = Field(default_factory=list)
    attrs: dict[str, Any] = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)
    locks: dict[str, str] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)
    desc: str | None = None


class RoomEntity(EntityBase):
    """A room."""

    kind: Literal["room"]


class ExitEntity(EntityBase):
    """An exit between two rooms."""

    kind: Literal["exit"]
    location: Ref
    destination: Ref


class ObjectEntity(EntityBase):
    """A plain object; `location` may be a room or another object."""

    kind: Literal["object"]
    location: Ref | None = None
    home: Ref | None = None


class PrototypeEntity(EntityBase):
    """A reusable template; applied in a later milestone."""

    kind: Literal["prototype"]


Entity = Annotated[
    RoomEntity | ExitEntity | ObjectEntity | PrototypeEntity,
    Field(discriminator="kind"),
]


class Bundle(BaseModel):
    """One YAML file's worth of content."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    zone: str | None = None
    entities: list[Entity]

    @model_validator(mode="after")
    def _check_schema_version(self) -> Bundle:
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"unsupported schema_version {self.schema_version}; "
                f"supported versions: {SUPPORTED_SCHEMA_VERSIONS}"
            )
        return self


def ref_target(ref: str) -> str:
    """Return the entity id a `@ref` points at."""
    return ref[1:]
