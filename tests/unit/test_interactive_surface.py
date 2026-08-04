from __future__ import annotations

from click.testing import CliRunner

from salt_config_cli.cli.main import cli


def test_no_args_renders_scc_dashboard(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0
    assert "Salt Config CLI" in result.output
    assert "Quick start" in result.output
    assert "Discover commands" in result.output
    assert "scc fs-list" not in result.output  # launch screen stays focused


def test_every_top_level_help_page_loads() -> None:
    runner = CliRunner()
    failures = []
    for name in cli.commands:
        result = runner.invoke(cli, [name, "--help"])
        if result.exit_code != 0:
            failures.append((name, result.output, repr(result.exception)))
    assert not failures


def test_run_is_safe_by_default() -> None:
    result = CliRunner().invoke(cli, ["run", "--help"])
    assert result.exit_code == 0
    assert "[default: test]" in result.output
    assert "--no-test" in result.output
    assert "apply changes" in result.output
    assert "--yes" in result.output


def test_discovery_search_and_examples_are_network_free() -> None:
    runner = CliRunner()
    search = runner.invoke(cli, ["search", "pillar"])
    assert search.exit_code == 0
    assert "pillar-list" in search.output
    examples = runner.invoke(cli, ["examples", "--topic", "fleet"])
    assert examples.exit_code == 0
    assert "fleet_settings" in examples.output


def test_tutorial_non_interactive() -> None:
    result = CliRunner().invoke(cli, ["tutorial", "--non-interactive"])
    assert result.exit_code == 0
    assert "Configure Git sources once" in result.output
    assert "test=True" in result.output
    assert "approved-manifest" not in result.output
    assert "approved and merged in Git" in result.output
