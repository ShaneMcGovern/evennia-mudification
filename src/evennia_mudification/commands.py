"""The in-game `mudification` command."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, ClassVar

from django.conf import settings
from evennia.commands.command import Command

from evennia_mudification import runtime
from evennia_mudification.apply import apply_plan
from evennia_mudification.compile import ContentIndex
from evennia_mudification.deferred import run_deferred
from evennia_mudification.identity import find_entity_object, managed_ids
from evennia_mudification.loading import load_content
from evennia_mudification.models import ref_target
from evennia_mudification.plan import build_plan
from evennia_mudification.proto import register_prototypes
from evennia_mudification.prune import execute_prune, plan_prune, resolve_fallback


class CmdMudification(Command):  # type: ignore[misc]  # Evennia ships no py.typed
    """
    Inspect and apply YAML world content.

    Usage:
      mudification validate
      mudification plan
      mudification apply
      mudification apply confirm
      mudification prune
      mudification prune confirm
      mudification status
    """

    key = "mudification"
    aliases: ClassVar[list[str]] = ["evennia_mudification"]
    locks = "cmd:perm(Developer)"
    help_category = "Building"

    def func(self) -> None:
        args = self.args.strip().split()
        subcommand = args[0] if args else "status"
        if subcommand == "validate":
            index = self._load()
            if index is not None:
                self.msg(f"{len(index.entities)} entities valid.")
        elif subcommand == "plan":
            index = self._load()
            if index is not None:
                self.msg(build_plan(index, resolve_ref=self._resolve_ref).render())
        elif subcommand == "apply":
            self._apply(confirm=len(args) > 1 and args[1] == "confirm")
        elif subcommand == "prune":
            self._prune(confirm=len(args) > 1 and args[1] == "confirm")
        elif subcommand == "status":
            self._status()
        else:
            self.msg(
                f"unknown subcommand '{subcommand}'; try validate, plan, apply, "
                "prune or status."
            )

    def _load(self) -> ContentIndex | None:
        content_path = getattr(settings, "MUDIFICATION_CONTENT_PATH", None)
        if not content_path:
            self.msg("MUDIFICATION_CONTENT_PATH is not set.")
            return None
        index, findings = load_content(Path(content_path), check_evennia=True)
        load_error = next(
            (finding for finding in findings if finding.code == "load-error"), None
        )
        if load_error is not None:
            self.msg(f"content load failed: {load_error.message}")
            return None
        errors = [finding for finding in findings if finding.severity == "error"]
        if errors:
            for finding in errors:
                self.msg(finding.render())
            self.msg(f"{len(errors)} validation errors; nothing was applied.")
            return None
        # Every successful load is also the latest validation, so `status`
        # reports what this run saw. Prototype registration is deliberately not
        # here: inspection commands must not mutate the prototype namespace.
        runtime.LAST_VALIDATION = runtime.ValidationSummary(
            content_path=str(content_path),
            entity_count=len(index.entities),
            warnings=[finding for finding in findings if finding.severity == "warning"],
        )
        return index

    def _resolve_ref(self, ref: str) -> Any:
        obj = find_entity_object(ref_target(ref))
        if obj is None:
            raise LookupError(f"reference '{ref}' has not been applied yet")
        return obj

    def _apply(self, *, confirm: bool) -> None:
        index = self._load()
        if index is None:
            return
        plan = build_plan(index, resolve_ref=self._resolve_ref)
        if plan.is_empty():
            self.msg("no changes")
            return
        if not confirm:
            self.msg(plan.render())
            self.msg("run 'mudification apply confirm' to apply these changes.")
            return
        register_prototypes(index)
        self._run(
            partial(
                apply_plan,
                plan,
                index=index,
                resolve_ref=self._resolve_ref,
                caller=self.caller,
            ),
            on_return=partial(self._report_applied, entity_count=len(index.entities)),
            on_error=self._report_failed("apply"),
            off_thread="applying off-thread; results will follow.",
        )

    def _report_applied(self, report: Any, *, entity_count: int) -> None:
        self.msg(report.render())
        if not report.ok:
            self.msg("some entities failed; fix the content and re-run apply.")
        else:
            runtime.LAST_APPLIED = entity_count

    def _report_failed(self, action: str) -> Callable[[Exception], None]:
        def _inner(err: Exception) -> None:
            get_message = getattr(err, "getErrorMessage", None)
            message = get_message() if get_message is not None else str(err)
            self.msg(f"{action} failed: {message}")

        return _inner

    def _run(
        self,
        work: Callable[[], Any],
        *,
        on_return: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        off_thread: str,
    ) -> None:
        """Start one apply or prune, holding the single run slot meanwhile."""
        if not runtime.claim_run():
            self.msg("an apply or prune is already running; wait for it to finish.")
            return
        try:
            deferred = run_deferred(
                work,
                at_return=self._releasing(on_return),
                at_err=self._releasing(on_error),
            )
        except Exception:
            runtime.release_run()
            raise
        if deferred:
            self.msg(off_thread)

    def _releasing(self, callback: Callable[..., None]) -> Callable[..., None]:
        def _inner(*args: Any, **kwargs: Any) -> None:
            try:
                callback(*args, **kwargs)
            finally:
                runtime.release_run()

        return _inner

    def _prune(self, *, confirm: bool) -> None:
        index = self._load()
        if index is None:
            return
        fallback = resolve_fallback()
        prune_plan = plan_prune(managed_ids() - set(index.entities), fallback=fallback)
        if prune_plan.errors:
            self.msg(prune_plan.render())
            return
        if not confirm:
            self.msg(prune_plan.render())
            self.msg("run 'mudification prune confirm' to execute these changes.")
            return
        # Confirmed runs keep the module-prototype namespace in step with the
        # content: declared templates register, removed ones deregister.
        register_prototypes(index)
        self._run(
            partial(execute_prune, prune_plan),
            on_return=lambda report: self.msg(report.render()),
            on_error=self._report_failed("prune"),
            off_thread="pruning off-thread; results will follow.",
        )

    def _status(self) -> None:
        summary = runtime.LAST_VALIDATION
        if summary is None:
            self.msg("no validation has run yet; run 'mudification validate'.")
        else:
            self.msg(
                f"last validation: {summary.entity_count} entities from "
                f"{summary.content_path} ({len(summary.errors)} errors, "
                f"{len(summary.warnings)} warnings)"
            )
        self.msg(f"managed entities in the database: {len(managed_ids())}")
        if runtime.LAST_APPLIED is not None:
            self.msg(f"last applied: {runtime.LAST_APPLIED} entities")
        content_path = getattr(settings, "MUDIFICATION_CONTENT_PATH", None)
        if content_path:
            index, findings = load_content(Path(content_path), check_evennia=False)
            errors = [finding for finding in findings if finding.severity == "error"]
            if errors:
                for finding in errors:
                    self.msg(finding.render())
            else:
                self.msg(f"retirements: {len(managed_ids() - set(index.entities))}")
                self.msg(f"source bundles: {len(index.sources)}")
