"""Apply a plan to the live database through Evennia's spawner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evennia.prototypes import spawner

from evennia_mudification.compile import ContentIndex
from evennia_mudification.identity import find_entity_object
from evennia_mudification.plan import Plan, PlannedChange
from evennia_mudification.proto import RefResolver, entity_to_prototype

_KIND_ORDER = {"room": 0, "exit": 1, "object": 2}


@dataclass
class EntityResult:
    """Outcome for one entity."""

    entity_id: str
    action: str
    ok: bool
    error: str | None = None

    def render(self) -> str:
        status = "ok" if self.ok else f"FAILED: {self.error}"
        return f"{self.action} {self.entity_id}: {status}"


@dataclass
class ApplyReport:
    """Outcomes for a whole apply run."""

    results: list[EntityResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.results)

    def render(self) -> str:
        if not self.results:
            return "nothing to apply"
        return "\n".join(result.render() for result in self.results)


def apply_plan(
    plan: Plan,
    *,
    index: ContentIndex,
    resolve_ref: RefResolver,
    caller: Any = None,
) -> ApplyReport:
    """Create and update entities, isolating per-entity failures.

    Creates run in passes so an object placed inside another object applies in
    one run regardless of declaration order: a ``LookupError`` (a reference
    not applied yet) defers that entity to the next pass, while other
    exceptions report a failure immediately. Passes repeat until no create
    succeeds, at which point the remaining deferred entities are reported as
    failed with their ``LookupError``. Updates run afterwards, unchanged.
    """
    report = ApplyReport()
    pending: list[PlannedChange] = sorted(
        (change for change in plan.changes if change.action == "create"),
        key=lambda change: _KIND_ORDER[index.entities[change.entity_id].kind],
    )
    while pending:
        deferred: list[tuple[PlannedChange, LookupError]] = []
        progress = False
        for change in pending:
            entity = index.entities[change.entity_id]
            try:
                prototype = entity_to_prototype(
                    entity, index=index, resolve_ref=resolve_ref
                )
                spawner.spawn(prototype, caller=caller)
            except LookupError as err:
                deferred.append((change, err))
            except Exception as err:  # per-entity isolation is deliberate
                report.results.append(
                    EntityResult(
                        change.entity_id, change.action, ok=False, error=str(err)
                    )
                )
            else:
                report.results.append(
                    EntityResult(change.entity_id, change.action, ok=True)
                )
                progress = True
        if not deferred:
            break
        if not progress:
            for change, deferred_error in deferred:
                report.results.append(
                    EntityResult(
                        change.entity_id,
                        change.action,
                        ok=False,
                        error=str(deferred_error),
                    )
                )
            break
        pending = [change for change, _ in deferred]

    updates = [change for change in plan.changes if change.action == "update"]
    for change in updates:
        entity = index.entities[change.entity_id]
        try:
            prototype = entity_to_prototype(
                entity, index=index, resolve_ref=resolve_ref
            )
            obj = find_entity_object(change.entity_id)
            spawner.batch_update_objects_with_prototype(
                prototype, objects=[obj], caller=caller
            )
            report.results.append(
                EntityResult(change.entity_id, change.action, ok=True)
            )
        except Exception as err:  # per-entity isolation is deliberate
            report.results.append(
                EntityResult(change.entity_id, change.action, ok=False, error=str(err))
            )
    return report
