"""Regression coverage for named connection profiles and config UX."""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from salt_config_cli.cli.main import cli
from salt_config_cli.core.config import ProfileConfigStore, SaltConfigSettings


def invoke_with_config(runner: CliRunner, config: Path, args: list[str], **kwargs):
    return runner.invoke(cli, ["--config-file", str(config), *args], **kwargs)


def test_configure_profile_list_show_and_use(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    runner = CliRunner()

    created = invoke_with_config(
        runner,
        config,
        [
            "configure",
            "--name", "lab",
            "--server", "https://raas.lab.example",
            "--username", "root",
            "--no-verify",
            "--environment", "fleet_mgmt",
            "--target", "lab-*",
            "--non-interactive",
            "--no-test",
        ],
    )
    assert created.exit_code == 0, created.output

    saved = ProfileConfigStore(config).load()
    assert saved.default_profile == "lab"
    assert saved.profiles["lab"].server_url == "https://raas.lab.example"
    assert saved.profiles["lab"].default_environment == "fleet_mgmt"
    assert saved.profiles["lab"].ssl_verify is False

    listed = invoke_with_config(runner, config, ["profile", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    payload = json.loads(listed.output)
    assert payload["default_profile"] == "lab"
    assert payload["profiles"][0]["name"] == "lab"

    shown = invoke_with_config(runner, config, ["profile", "show", "lab", "--json"])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["server_url"] == "https://raas.lab.example"


def test_global_profile_selects_effective_configuration(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "default_profile": "lab",
                "profiles": {
                    "lab": {"server_url": "https://lab.example", "username": "lab-user"},
                    "prod": {"server_url": "https://prod.example", "username": "prod-user"},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--config-file", str(config), "--profile", "prod", "config", "show", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["profile_name"] == "prod"
    assert payload["server_url"] == "https://prod.example"


def test_legacy_flat_config_is_exposed_as_default_profile(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "server_url": "https://legacy.example",
                "username": "legacy-user",
                "ssl_verify": False,
                "password": "must-not-load",
            }
        ),
        encoding="utf-8",
    )
    settings = SaltConfigSettings.load_from_file(str(config))
    assert settings.profile_name == "default"
    assert settings.config_format == "legacy-flat"
    assert settings.server_url == "https://legacy.example"
    assert settings.password is None

    migrated = ProfileConfigStore(config).load()
    assert migrated.profiles["default"].username == "legacy-user"


def test_config_set_and_unset(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    store = ProfileConfigStore(config)
    from salt_config_cli.core.config import ConnectionProfile

    store.upsert_profile(
        "lab",
        ConnectionProfile(server_url="https://lab.example", username="root"),
        make_default=True,
    )
    runner = CliRunner()

    updated = invoke_with_config(runner, config, ["config", "set", "timeout", "120"])
    assert updated.exit_code == 0, updated.output
    assert store.load().profiles["lab"].timeout == 120

    set_ca = invoke_with_config(runner, config, ["config", "set", "ca_bundle", "/tmp/ca.pem"])
    assert set_ca.exit_code == 0, set_ca.output
    unset_ca = invoke_with_config(runner, config, ["config", "unset", "ca_bundle"])
    assert unset_ca.exit_code == 0, unset_ca.output
    assert store.load().profiles["lab"].ca_bundle is None


def test_connect_can_create_named_profile_non_interactively(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    runner = CliRunner()
    import importlib
    main_module = importlib.import_module("salt_config_cli.cli.main")
    monkeypatch.setattr(main_module, "keychain_available", lambda: False)
    result = runner.invoke(
        cli,
        [
            "--config-file", str(config),
            "connect",
            "--name", "staging",
            "--server", "https://staging.example",
            "--username", "root",
            "--password-stdin",
            "--no-test",
        ],
        input="secret\n",
    )
    assert result.exit_code == 0, result.output
    saved = ProfileConfigStore(config).load()
    assert saved.default_profile == "staging"
    assert saved.profiles["staging"].server_url == "https://staging.example"
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert "password" not in raw["profiles"]["staging"]
    assert "csp_api_token" not in raw["profiles"]["staging"]


def test_profile_and_config_group_help_are_themed() -> None:
    runner = CliRunner()
    for group, command in [("profile", "profile list"), ("config", "config show")]:
        result = runner.invoke(cli, ["help", group])
        assert result.exit_code == 0, result.output
        assert "SALT CONFIG CLI" in result.output
        assert f"scc {group} <COMMAND> [ARGS]" in result.output
        assert f"scc {command}" in result.output
        assert "scc run.py" not in result.output
        assert "scc -m" not in result.output
