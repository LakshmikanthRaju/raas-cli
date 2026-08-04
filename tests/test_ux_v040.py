"""Regression tests for the unified v0.4 interactive UX."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import click
from click.testing import CliRunner

from salt_config_cli.cli.main import cli


class _CatalogClient:
    def close(self) -> None:
        return None

    def call(self, resource: str, method: str, **kwargs):
        if (resource, method) == ("pillar", "get_pillars"):
            ret = {
                "results": [
                    {
                        "name": "dns",
                        "uuid": "pillar-1234567890",
                        "pillar_type": "static",
                        "pillar": {"dns": {"servers": ["192.0.2.10"]}},
                    }
                ]
            }
        elif (resource, method) == ("tgt", "get_target_group"):
            ret = {
                "results": [
                    {
                        "name": "Fleet",
                        "uuid": "target-1234567890",
                        "desc": "Fleet target group",
                        "minion_count": 2,
                        "tgt": {"*": {"tgt": "node-1,node-2", "tgt_type": "list"}},
                        "pillars": [{"name": "dns", "uuid": "pillar-1234567890"}],
                    }
                ]
            }
        elif (resource, method) == ("job", "get_jobs"):
            ret = {
                "results": [
                    {
                        "name": "fleet-ping",
                        "uuid": "job-1234567890",
                        "fun": "test.ping",
                        "cmd": "local",
                        "desc": "Safe fleet connectivity check",
                        "tgt_uuid": "target-1234567890",
                    }
                ]
            }
        else:
            ret = {}
        return SimpleNamespace(success=True, error=None, ret=ret)


def test_help_keeps_the_scc_visual_theme() -> None:
    result = CliRunner().invoke(cli, ["help"])
    assert result.exit_code == 0
    assert "SALT CONFIG CLI" in result.output
    assert "Getting started" in result.output
    assert "Global options" in result.output
    assert "Start here" in result.output
    assert "╭" in result.output


def test_focused_help_has_syntax_options_safety_and_examples() -> None:
    result = CliRunner().invoke(cli, ["help", "run"])
    assert result.exit_code == 0
    assert "Syntax" in result.output
    assert "Safety & execution" in result.output
    assert "State execution is dry-run by default" in result.output
    assert "Examples" in result.output
    assert "[default: test]" in result.output


def test_exec_defaults_to_interactive_text_output() -> None:
    ctx = click.Context(cli, info_name="scc")
    command = cli.get_command(ctx, "exec")
    assert command is not None
    output_option = next(param for param in command.params if param.name == "output_fmt")
    assert output_option.default == "text"


def test_catalog_commands_render_tables_and_result_cards() -> None:
    runner = CliRunner()
    commands = [
        (["pillar-list", "--server", "https://raas.example.test", "--username", "user"], "Pillar inventory loaded"),
        (["target-group-list", "--server", "https://raas.example.test", "--username", "user"], "Target-group inventory loaded"),
        (["job-list", "--server", "https://raas.example.test", "--username", "user"], "Saved-job inventory loaded"),
    ]
    for args, expected in commands:
        with patch("salt_config_cli.cli.main.connect_client", return_value=_CatalogClient()):
            result = runner.invoke(cli, args)
        assert result.exit_code == 0, result.output
        assert expected in result.output
        assert "Next steps" in result.output
        assert "╭" in result.output
