"""The demo seeding command is opt-in and environment gated (no database needed)."""

from __future__ import annotations

import pytest

from app.cli import build_parser, seed_demo_environment


class TestDemoSeedGuard:
    @pytest.mark.parametrize("environment", ["local", "test", "ci"])
    def test_development_environments_are_allowed(self, environment: str) -> None:
        assert seed_demo_environment(environment) is True

    @pytest.mark.parametrize("environment", ["staging", "production", "", "unknown"])
    def test_deployed_environments_are_refused(self, environment: str) -> None:
        assert seed_demo_environment(environment) is False

    def test_command_requires_a_company(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["seed-demo"])

    def test_command_defaults_to_not_forcing(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["seed-demo", "--company", "TOUCHE Trading"])
        assert args.company == "TOUCHE Trading"
        assert args.force is False
