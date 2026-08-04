"""Regression coverage for professional runtime-selectable themes."""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from salt_config_cli.cli.main import cli


def invoke(runner: CliRunner, config: Path, args: list[str], **kwargs):
    return runner.invoke(cli, ["--config-file", str(config), *args], **kwargs)


def test_theme_catalog_is_themed_and_complete(tmp_path: Path) -> None:
    result = invoke(CliRunner(), tmp_path / "config.yaml", ["theme", "list"])
    assert result.exit_code == 0, result.output
    for name in ("ocean", "enterprise", "graphite", "forest", "amber", "high-contrast", "plain"):
        assert name in result.output
    assert "Professional themes" in result.output
    assert "╭" in result.output


def test_one_shot_plain_help_uses_normal_click_output() -> None:
    result = CliRunner().invoke(cli, ["--theme", "plain", "help"])
    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output
    assert "theme" in result.output
    assert "╭" not in result.output
    assert "SALT CONFIG CLI" not in result.output


def test_plain_alias_none_is_supported() -> None:
    result = CliRunner().invoke(cli, ["--theme", "none", "status"])
    assert result.exit_code == 0, result.output
    assert "scc status - Workspace and connection status" in result.output
    assert "╭" not in result.output


def test_global_theme_selection_and_current_json(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    runner = CliRunner()
    selected = invoke(runner, config, ["theme", "use", "graphite"])
    assert selected.exit_code == 0, selected.output
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert raw["theme"] == "graphite"

    current = invoke(runner, config, ["theme", "current", "--json"])
    assert current.exit_code == 0, current.output
    payload = json.loads(current.output)
    assert payload["theme"] == "graphite"
    assert payload["source"] == "global configuration"


def test_disable_persists_plain_and_enable_restores_theme(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    runner = CliRunner()
    disabled = invoke(runner, config, ["theme", "disable"])
    assert disabled.exit_code == 0, disabled.output
    assert yaml.safe_load(config.read_text(encoding="utf-8"))["theme"] == "plain"

    help_result = invoke(runner, config, ["help"])
    assert help_result.exit_code == 0, help_result.output
    assert "Usage:" in help_result.output
    assert "╭" not in help_result.output

    enabled = invoke(runner, config, ["theme", "enable", "forest"])
    assert enabled.exit_code == 0, enabled.output
    assert yaml.safe_load(config.read_text(encoding="utf-8"))["theme"] == "forest"


def test_profile_theme_overrides_global_theme(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "default_profile": "prod",
                "theme": "enterprise",
                "profiles": {
                    "lab": {"server_url": "https://lab.example", "username": "root", "theme": "forest"},
                    "prod": {"server_url": "https://prod.example", "username": "root"},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    lab = runner.invoke(cli, ["--config-file", str(config), "--profile", "lab", "theme", "current", "--json"])
    assert lab.exit_code == 0, lab.output
    lab_payload = json.loads(lab.output)
    assert lab_payload["theme"] == "forest"
    assert lab_payload["source"] == "profile 'lab'"

    prod = runner.invoke(cli, ["--config-file", str(config), "--profile", "prod", "theme", "current", "--json"])
    assert prod.exit_code == 0, prod.output
    prod_payload = json.loads(prod.output)
    assert prod_payload["theme"] == "enterprise"
    assert prod_payload["source"] == "global configuration"


def test_environment_theme_override_has_highest_persisted_precedence(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump({"version": 2, "default_profile": "default", "theme": "plain", "profiles": {}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SCC_THEME", "amber")
    result = invoke(CliRunner(), config, ["theme", "current", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["theme"] == "amber"
    assert payload["source"] == "environment (SCC_THEME)"


def test_theme_preview_does_not_change_persisted_selection(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    runner = CliRunner()
    invoke(runner, config, ["theme", "use", "enterprise"])
    preview = invoke(runner, config, ["theme", "preview", "amber"])
    assert preview.exit_code == 0, preview.output
    assert yaml.safe_load(config.read_text(encoding="utf-8"))["theme"] == "enterprise"


def test_config_set_accepts_theme_field(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "default_profile": "lab",
                "theme": "ocean",
                "profiles": {"lab": {"server_url": "https://lab.example", "username": "root"}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    result = invoke(CliRunner(), config, ["config", "set", "theme", "high-contrast"])
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert raw["profiles"]["lab"]["theme"] == "high-contrast"
