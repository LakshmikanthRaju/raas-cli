"""Regression coverage for the restored interactive command surface."""

from __future__ import annotations

import ast
from pathlib import Path

from click.testing import CliRunner
from rich.text import Text

from salt_config_cli.cli.main import cli
from salt_config_cli.ui import kv_table
from salt_config_cli.ui.theme import ICONS


def test_kv_table_accepts_ordered_row_pairs() -> None:
    """The status screen passes a list of pairs, not only a mapping."""
    kv_table(
        "Workspace",
        [
            ("Working directory", "/tmp/workspace"),
            ("Status", Text(" READY ", style="scc.success")),
        ],
    )


def test_every_direct_icon_reference_exists() -> None:
    """Prevent runtime KeyError failures from missing theme icon aliases."""
    package_root = Path(__file__).parents[1] / "salt_config_cli"
    referenced: set[str] = set()

    for source_file in package_root.rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript):
                continue
            if not isinstance(node.value, ast.Name) or node.value.id != "ICONS":
                continue
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                referenced.add(node.slice.value)

    assert referenced <= ICONS.keys(), f"Missing icon aliases: {sorted(referenced - ICONS.keys())}"


def test_status_command_does_not_crash(tmp_path: Path, monkeypatch) -> None:
    """Regression for list.items() failure reported by a Python 3.14 user."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(cli, ["status", "--no-color"])

    assert result.exit_code == 0, result.output
    assert result.exception is None


def test_connect_command_uses_available_icons(tmp_path: Path, monkeypatch) -> None:
    """Regression for missing `plug` and `shield` icon aliases."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "connect",
            "--server",
            "https://127.0.0.1",
            "--csp-token",
            "test-token",
            "--no-test",
            "--no-save",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.exception is None
