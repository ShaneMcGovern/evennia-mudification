"""Smoke-test that Evennia runs under pytest without a game directory."""

from evennia.utils import create
from evennia.utils.test_resources import BaseEvenniaTestCase


class TestHarness(BaseEvenniaTestCase):
    def test_create_object(self) -> None:
        obj = create.create_object(
            "evennia.objects.objects.DefaultObject", key="harness"
        )
        assert obj.key == "harness"
