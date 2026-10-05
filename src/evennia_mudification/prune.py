"""Report and execute retirement of managed content, with evacuation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

from evennia_mudification.apply import EntityResult
from evennia_mudification.findings import Finding
from evennia_mudification.identity import ENTITY_TAG_CATEGORY, find_entity_object


def resolve_fallback() -> Any:
    """Resolve the configured fallback room, or None when unavailable.

    Evennia's dbref helper returns non-dbref input unchanged, so a setting
    holding something else must not be mistaken for a room.
    """
    from evennia.objects.models import ObjectDB
    from evennia.utils.utils import dbid_to_obj

    dbref = getattr(settings, "MUDIFICATION_FALLBACK_ROOM", None) or getattr(
        settings, "DEFAULT_HOME", None
    )
    if not dbref:
        return None
    try:
        resolved = dbid_to_obj(str(dbref), ObjectDB)
    except Exception:
        return None
    if not isinstance(resolved, ObjectDB) and not hasattr(resolved, "pk"):
        return None
    return resolved


@dataclass
class Evacuation:
    """One occupant that must move before its container is destroyed."""

    occupant: Any
    destination: Any
    reason: str  # "home" | "fallback"

    def render(self) -> str:
        return f"evacuate {self.occupant.key} -> {self.destination.key} ({self.reason})"


@dataclass
class PrunePlan:
    """What pruning would do: retirements, evacuations, and refusal errors."""

    retirements: list[str] = field(default_factory=list)
    evacuations: list[Evacuation] = field(default_factory=list)
    errors: list[Finding] = field(default_factory=list)

    def render(self) -> str:
        if self.errors:
            return "\n".join(finding.render() for finding in self.errors)
        if not self.retirements:
            return "no retirements"
        lines = [f"retire {entity_id}" for entity_id in self.retirements]
        lines += [evacuation.render() for evacuation in self.evacuations]
        return "\n".join(lines)


def _is_retired(obj: Any, retired: set[str]) -> bool:
    """True when the object carries a managed id that this run retires."""
    managed = set(obj.tags.get(category=ENTITY_TAG_CATEGORY, return_list=True))
    return bool(managed & retired)


def plan_prune(retired_ids: set[str], *, fallback: Any) -> PrunePlan:
    """Build the retirement/evacuation plan; refuses when recovery is impossible.

    Occupants that are themselves retired are skipped: this run destroys them,
    so evacuating them first would be pointless. A retired room's surviving
    occupants go to their home when it is live and not itself retiring,
    otherwise to the fallback; a retired object's surviving contents go to the
    fallback regardless of home. The fallback must itself be a live room this
    run is not retiring. When such occupants exist and no usable fallback
    exists, the plan refuses rather than stranding them.
    """
    from evennia.objects.objects import DefaultRoom

    plan = PrunePlan(retirements=sorted(retired_ids))
    orphaned: list[Any] = []
    for entity_id in plan.retirements:
        obj = find_entity_object(entity_id)
        if obj is None:
            continue
        is_room = isinstance(obj, DefaultRoom)
        for occupant in list(obj.contents):
            if _is_retired(occupant, retired_ids):
                continue
            home = getattr(occupant, "home", None)
            if is_room and home is not None and not _is_retired(home, retired_ids):
                plan.evacuations.append(Evacuation(occupant, home, "home"))
            else:
                orphaned.append(occupant)
    if orphaned:
        usable_fallback = (
            fallback is not None
            and isinstance(fallback, DefaultRoom)
            and not _is_retired(fallback, retired_ids)
        )
        if not usable_fallback:
            plan.errors.append(
                Finding(
                    "error",
                    "fallback-missing",
                    "no resolvable fallback room (MUDIFICATION_FALLBACK_ROOM / "
                    "DEFAULT_HOME) for "
                    + ", ".join(occupant.key for occupant in orphaned),
                    "prune",
                )
            )
        else:
            plan.evacuations.extend(
                Evacuation(occupant, fallback, "fallback") for occupant in orphaned
            )
    return plan


@dataclass
class PruneReport:
    """Per-entity outcomes of a prune run."""

    results: list[EntityResult] = field(default_factory=list)
    evacuated: int = 0
    destroyed: int = 0

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.results)

    def render(self) -> str:
        lines = [result.render() for result in self.results]
        lines.append(f"evacuated {self.evacuated}, destroyed {self.destroyed}")
        return "\n".join(lines)


def execute_prune(prune_plan: PrunePlan) -> PruneReport:
    """Evacuate every occupant, then destroy the retired objects.

    All evacuations run before any destruction. If any evacuation fails,
    destruction is skipped entirely, so a container is never deleted while an
    occupant is still stranded in it; failures are isolated per item and
    reported. A destruction whose delete is vetoed is a failure row and is not
    counted as destroyed, and a retirement whose object is already gone is
    silently skipped.
    """
    report = PruneReport()
    for evacuation in prune_plan.evacuations:
        try:
            evacuation.occupant.location = evacuation.destination
            report.evacuated += 1
        except Exception as err:  # per-occupant isolation is deliberate
            report.results.append(
                EntityResult(
                    evacuation.occupant.key, "evacuate", ok=False, error=str(err)
                )
            )
    if not report.ok:
        # A missed evacuation must not be followed by a destruction whose
        # delete-time relocation would move the occupant by its own rules.
        return report
    for entity_id in prune_plan.retirements:
        obj = find_entity_object(entity_id)
        if obj is None:
            continue
        try:
            deleted = obj.delete()
        except Exception as err:  # per-entity isolation is deliberate
            report.results.append(
                EntityResult(entity_id, "destroy", ok=False, error=str(err))
            )
            continue
        if deleted is False:
            report.results.append(
                EntityResult(
                    entity_id, "destroy", ok=False, error="deletion was vetoed"
                )
            )
        else:
            report.destroyed += 1
            report.results.append(EntityResult(entity_id, "destroy", ok=True))
    return report
