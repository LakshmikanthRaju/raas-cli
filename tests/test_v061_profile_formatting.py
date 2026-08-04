"""Regression coverage for v0.6.1 profile migration and responsive UX."""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from salt_config_cli.cli.main import cli


def invoke(config: Path, args: list[str], **kwargs):
    return CliRunner().invoke(cli, ["--config-file", str(config), *args], **kwargs)


def test_hybrid_v060_config_is_migrated_and_backed_up(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "default_profile": "default",
                "theme": "ocean",
                "profiles": {},
                "server_url": "https://192.0.2.10",
                "username": "root",
                "ssl_verify": False,
                "ops_server_url": "https://ops.example",
                "ops_username": "ops-reader",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = invoke(config, ["profile", "list", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["default_profile"] == "default"
    assert payload["profiles"][0]["server"] == "https://192.0.2.10"

    normalized = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert "server_url" not in normalized
    assert "username" not in normalized
    assert normalized["profiles"]["default"]["username"] == "root"
    assert normalized["profiles"]["default"]["ops_server_url"] == "https://ops.example"
    assert normalized["profiles"]["default"]["ops_username"] == "ops-reader"
    assert config.with_suffix(".yaml.pre-v2.bak").exists()


def test_configure_works_after_hybrid_profile_migration(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "default_profile": "default",
                "theme": "enterprise",
                "profiles": {},
                "server_url": "https://legacy.example",
                "username": "root",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = invoke(
        config,
        [
            "configure",
            "--name",
            "dev-saif",
            "--server",
            "https://dev.example",
            "--username",
            "root",
            "--non-interactive",
            "--no-test",
        ],
    )

    assert result.exit_code == 0, result.output
    saved = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert set(saved["profiles"]) == {"default", "dev-saif"}
    assert saved["default_profile"] == "dev-saif"
    assert "Legacy configuration upgraded" in result.output


def test_configuration_groups_without_subcommands_show_help_not_error(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    runner = CliRunner()

    for group in ("profile", "config", "theme"):
        result = runner.invoke(
            cli,
            ["--config-file", str(config), group],
            terminal_width=160,
        )
        assert result.exit_code == 0, result.output
        assert "SALT CONFIG CLI" in result.output
        assert f"scc {group} <COMMAND> [ARGS]" in result.output
        assert "Error" not in result.output


def test_profile_table_uses_readable_cards_in_narrow_terminals(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "default_profile": "lab",
                "profiles": {
                    "lab": {
                        "server_url": "https://lab.example",
                        "username": "root",
                        "ssl_verify": False,
                    },
                    "production-long-profile-name": {
                        "server_url": "https://raas-production-long-hostname.example.com",
                        "username": "service-account-production",
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = invoke(config, ["profile", "list"], terminal_width=80)

    assert result.exit_code == 0, result.output
    assert "Name: lab" in result.output
    assert "Name: production-long-profile-name" in result.output
    assert "TLS verification" in result.output
    assert "Environm" not in result.output


def test_profile_validation_errors_are_concise(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "default_profile": "lab",
                "profiles": {
                    "lab": {
                        "server_url": "https://lab.example",
                        "server_urll": "https://typo.example",
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = invoke(config, ["profile", "list"])

    assert result.exit_code == 2
    assert "profiles.lab.server_urll: unsupported field" in result.output
    assert "errors.pydantic.dev" not in result.output
