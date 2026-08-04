#!/usr/bin/env python3
"""Offline release checks for accidental secrets and packaging regressions."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if (ROOT / ".scc").exists():
        fail("repository contains a workspace .scc directory")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "salt_config_cli" / "__init__.py").read_text(encoding="utf-8")
    project_version = re.search(r'^version = "([^"]+)"', pyproject, re.M)
    module_version = re.search(r'^__version__ = "([^"]+)"', init, re.M)
    if not project_version or not module_version or project_version.group(1) != module_version.group(1):
        fail("pyproject and module versions do not match")

    banned_patterns = {
        "private key material": re.compile(
            r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"
        ),
        "GitHub access token": re.compile(
            r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
        ),
        "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    }
    scan_extensions = {".py", ".md", ".yaml", ".yml", ".toml", ".txt", ".sls", ".jinja"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in scan_extensions:
            continue
        if any(part in {"dist", "build", ".git", ".venv", ".idea", "__pycache__"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in banned_patterns.items():
            if pattern.search(text):
                fail(f"possible {label} in {path}")

    from salt_config_cli.cli.main import cli

    runner = CliRunner()
    help_pages = 0

    def check_help(group, path: list[str]) -> None:
        nonlocal help_pages
        result = runner.invoke(cli, [*path, "--help"])
        if result.exit_code != 0:
            label = " ".join(path)
            fail(f"help page failed for {label}: {result.output}\n{result.exception!r}")
        help_pages += 1
        commands = getattr(group, "commands", {})
        for name, subcommand in sorted(commands.items()):
            if getattr(subcommand, "hidden", False):
                continue
            check_help(subcommand, [*path, name])

    for name, command in sorted(cli.commands.items()):
        if getattr(command, "hidden", False):
            continue
        check_help(command, [name])

    dashboard = runner.invoke(cli, [])
    if dashboard.exit_code != 0 or "Quick start" not in dashboard.output:
        fail("launch dashboard smoke test failed")

    print(f"Release checks passed for salt-config-cli {project_version.group(1)} ({len(cli.commands)} top-level commands, {help_pages} help pages).")


if __name__ == "__main__":
    main()
