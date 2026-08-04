"""Additional operational commands built on the restored RaaS client."""
from __future__ import annotations

import json
import shlex
import sys
import time
from pathlib import Path
from typing import Any

import click
import yaml
from rich import box
from rich.panel import Panel
from rich.table import Table

from salt_config_cli.ui import (
    ICONS, command_header, confirm_destructive, empty_state, error as ui_error, mask_url,
    next_steps, result_summary, success, warn,
)
from salt_config_cli.ui.theme import console


def _parse_payload(data: str | None, data_file: str | None) -> dict[str, Any]:
    if data and data_file:
        raise click.ClickException("Use either --data or --data-file, not both")
    raw = Path(data_file).read_text(encoding="utf-8") if data_file else (data or "{}")
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise click.ClickException(f"Invalid JSON/YAML payload: {exc}") from exc
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise click.ClickException("RPC payload must be a JSON/YAML object")
    return parsed


def _render_any(value: Any, *, title: str | None = None) -> None:
    if isinstance(value, dict):
        table = Table(title=title, box=box.ROUNDED, show_header=True, header_style="scc.secondary")
        table.add_column("Field", style="scc.label", no_wrap=True)
        table.add_column("Value", style="scc.value", overflow="fold")
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                item = json.dumps(item, indent=2, default=str)
            table.add_row(str(key), str(item))
        console.print(table)
    elif isinstance(value, list):
        if not value:
            console.print("[scc.muted]No results.[/scc.muted]")
            return
        if all(isinstance(item, dict) for item in value):
            keys: list[str] = []
            for row in value:
                for key in row:
                    if key not in keys:
                        keys.append(key)
            keys = keys[:8]
            table = Table(title=title, box=box.ROUNDED, header_style="scc.secondary")
            for key in keys:
                table.add_column(key.replace("_", " ").title(), overflow="fold")
            for row in value:
                table.add_row(*(str(row.get(k, "")) for k in keys))
            console.print(table)
        else:
            console.print(Panel("\n".join(str(v) for v in value), title=title, border_style="scc.primary"))
    else:
        console.print(Panel(str(value), title=title, border_style="scc.primary"))


def register(group: click.Group, *, common_options, load_settings, connect_client, setup_logging) -> None:
    @group.command("system-info")
    @click.option("--json", "as_json", is_flag=True, help="Output machine-readable JSON.")
    @common_options
    def system_info(as_json, config, server, username, password, password_stdin, password_file,
                    password_prompt, csp_token, log_level, no_color):
        """Show RaaS versions, masters and license information."""
        setup_logging(log_level, no_color)
        settings = load_settings(config, server, username, password, csp_token,
                                 password_stdin=password_stdin, password_file=password_file,
                                 password_prompt=password_prompt)
        if not as_json:
            command_header(
                "system-info",
                "RaaS platform information",
                description="Inspect server version, connected Salt masters and license metadata.",
                icon="server",
                meta=[("Server", mask_url(settings.server_url)), ("User", settings.username or "CSP token")],
            )
        client = connect_client(settings, label="system information")
        try:
            payload = {
                "server": mask_url(settings.server_url),
                "version": client.get_versions(),
                "masters": client.get_masters(),
                "license": client.get_license(),
            }
            if as_json:
                console.print_json(json.dumps(payload, default=str))
                return
            success(f"Connected to {mask_url(settings.server_url)}")
            _render_any({"Server": payload["server"], "Version": payload["version"]}, title="RaaS")
            _render_any(payload["masters"], title="Salt Masters")
            _render_any(payload["license"] or {"status": "not returned"}, title="License")
            master_count = len(payload["masters"]) if isinstance(payload["masters"], list) else (len(payload["masters"]) if isinstance(payload["masters"], dict) else 0)
            result_summary(
                "System information loaded",
                status="success",
                message="RaaS responded successfully to version, master and license queries.",
                metrics=[(master_count, "masters", "primary")],
            )
            next_steps([
                "Browse server resources: `scc list`",
                "Inspect connectivity health: `scc doctor`",
                "Test minions: `scc exec test.ping --output text`",
            ])
        finally:
            client.close()

    @group.command("rpc")
    @click.argument("resource")
    @click.argument("method")
    @click.option("--data", default=None, help="RPC keyword arguments as JSON or YAML.")
    @click.option("--data-file", type=click.Path(exists=True, dir_okay=False), default=None)
    @click.option("--read-only", is_flag=True, help="Declare the call read-only; skips confirmation.")
    @click.option("--yes", is_flag=True, help="Confirm a potentially mutating call non-interactively.")
    @click.option("--json", "as_json", is_flag=True)
    @common_options
    def rpc_cmd(resource, method, data, data_file, read_only, yes, as_json, config, server,
                username, password, password_stdin, password_file, password_prompt, csp_token,
                log_level, no_color):
        """Call a raw RaaS RPC method as an expert escape hatch."""
        setup_logging(log_level, no_color)
        payload = _parse_payload(data, data_file)
        if not read_only and not yes:
            if not confirm_destructive(
                action=f"call {resource}.{method}",
                targets_summary="Raw RPC methods can mutate RaaS or minion state.",
                typed_phrase="rpc",
                auto_approve=False,
            ):
                raise click.ClickException("RPC call cancelled")
        settings = load_settings(config, server, username, password, csp_token,
                                 password_stdin=password_stdin, password_file=password_file,
                                 password_prompt=password_prompt)
        client = connect_client(settings, label="raw RPC")
        try:
            response = client.call(resource, method, **payload)
            if response.error:
                raise click.ClickException(response.error.get("message", str(response.error)))
            if as_json:
                console.print_json(json.dumps(response.ret, default=str))
            else:
                _render_any(response.ret, title=f"{resource}.{method}")
        finally:
            client.close()

    @group.command("shell")
    @click.option("--command", "initial_command", help="Run one SCC command first, then open the console.")
    @click.pass_context
    def shell_cmd(ctx: click.Context, initial_command: str | None):
        """Open an interactive command launcher for common RaaS operations."""
        if not sys.stdin.isatty():
            raise click.ClickException("The interactive shell requires a TTY")

        actions = [
            ("Connection profiles", "profile list", "List saved lab, staging and production connections"),
            ("Active configuration", "config show", "Inspect the effective profile and environment overrides"),
            ("Connection health", "status", "Verify workspace, credentials and RaaS reachability"),
            ("Deep diagnostics", "doctor", "Check DNS, TCP, TLS, authentication and RPC compatibility"),
            ("Browse resources", "list", "Discover minions, jobs, pillars and environments"),
            ("Browse file server", "fs-list", "Explore remote Salt environments and file trees"),
            ("Saved jobs", "job-list", "Review reusable RaaS operations"),
            ("Target groups", "target-group-list", "Review saved minion scopes"),
            ("Pillars", "pillar-list", "Review data and target-group assignments"),
            ("Ping all minions", "exec test.ping --target '*' --output text", "Run a safe connectivity check"),
            ("System information", "system-info", "View versions, masters and license metadata"),
        ]

        command_header(
            "shell",
            "Interactive RaaS operations console",
            description="Use a numbered shortcut or type any SCC command. Tab completion and persistent history are enabled when prompt-toolkit is available.",
            icon="sparkle",
            meta=[("Shortcuts", len(actions)), ("History", "~/.scc/history"), ("Exit", "exit or Ctrl-D")],
            mode=("INTERACTIVE", "black on #65b8ff"),
        )

        def show_menu() -> None:
            table = Table(box=box.SIMPLE, expand=True, header_style="scc.secondary", padding=(0, 1))
            table.add_column("#", style="scc.accent", justify="right", no_wrap=True, width=3)
            table.add_column("Operation", style="scc.strong", no_wrap=True, width=24)
            table.add_column("Command", style="scc.cmd", overflow="fold", width=40)
            table.add_column("Purpose", style="scc.value", overflow="fold")
            for idx, (label, command_line, purpose) in enumerate(actions, 1):
                table.add_row(str(idx), label, f"scc {command_line}", purpose)
            console.print(Panel(table, title=f"[scc.title]{ICONS['rocket']} Quick operations[/scc.title]", border_style="scc.primary", box=box.ROUNDED))
            console.print(
                "[scc.hint]Type a number, a normal command, `menu`, `help`, `clear`, or `exit`. "
                "Example: [scc.cmd]exec grains.get os --target <minion> --output text[/scc.cmd][/scc.hint]"
            )

        show_menu()

        session = None
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
            from prompt_toolkit.completion import WordCompleter
            from prompt_toolkit.history import FileHistory
            from prompt_toolkit.styles import Style

            history_path = Path.home() / ".scc" / "history"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            choices = sorted(set(group.commands) | {"menu", "help", "clear", "exit", "quit"})
            session = PromptSession(
                history=FileHistory(str(history_path)),
                auto_suggest=AutoSuggestFromHistory(),
                completer=WordCompleter(choices, ignore_case=True, sentence=True),
                complete_while_typing=False,
                style=Style.from_dict({
                    "prompt": "bold #65b8ff",
                    "rprompt": "#737b8c",
                }),
            )
        except Exception:
            session = None

        pending = initial_command
        while True:
            try:
                if pending is not None:
                    command_line = pending.strip()
                    pending = None
                elif session is not None:
                    command_line = session.prompt(
                        [("class:prompt", "scc ❯ ")],
                        rprompt=[("class:rprompt", "menu: ?  ·  exit: Ctrl-D")],
                    ).strip()
                else:
                    command_line = click.prompt("scc", type=str, default="", show_default=False).strip()
            except EOFError:
                console.print()
                result_summary("Interactive console closed", status="info", message="No remote operation was started by the exit action.")
                return
            except KeyboardInterrupt:
                console.print()
                warn("Input cancelled. Type `exit` to leave the console.")
                continue

            if not command_line:
                continue
            if command_line.startswith("scc "):
                command_line = command_line[4:].strip()

            lowered = command_line.casefold()
            if lowered in {"exit", "quit", "q"}:
                result_summary("Interactive console closed", status="success", message="Returning to your normal shell.")
                return
            if lowered in {"menu", "?"}:
                show_menu()
                continue
            if lowered == "clear":
                console.clear()
                command_header(
                    "shell", "Interactive RaaS operations console",
                    description="The screen was cleared; command history is still available with the Up arrow.",
                    icon="sparkle",
                )
                show_menu()
                continue
            if lowered == "help":
                command_line = "help"
            elif command_line.isdigit():
                selected = int(command_line)
                if selected < 1 or selected > len(actions):
                    warn(f"Choose a number from 1 to {len(actions)}.")
                    continue
                command_line = actions[selected - 1][1]

            try:
                args = shlex.split(command_line)
            except ValueError as exc:
                ui_error(f"Unable to parse command: {exc}", hint="Check quotes and escape characters, then retry.")
                continue
            if args and args[0] == "shell":
                warn("Nested interactive shells are not supported")
                continue

            console.rule(f"[scc.secondary]{ICONS['arrow']} scc {command_line}[/scc.secondary]", style="scc.primary")
            started = time.monotonic()
            exit_code = 0
            try:
                root_obj = ctx.find_root().obj or {}
                nested_args: list[str] = []
                if root_obj.get("config_path"):
                    nested_args.extend(["--config-file", str(root_obj["config_path"])])
                if root_obj.get("profile_explicit"):
                    nested_args.extend(["--profile", str(root_obj["profile_explicit"])])
                nested_args.extend(args)
                group.main(args=nested_args, prog_name="scc", standalone_mode=False)
            except SystemExit as exc:
                exit_code = int(exc.code or 0)
                if exit_code:
                    warn(f"Command exited with status {exit_code}")
            except click.ClickException as exc:
                exit_code = exc.exit_code
                ui_error(exc.format_message(), hint=f"Run `scc help {args[0]}` to review the syntax." if args else "Run `scc help`.")
            except KeyboardInterrupt:
                exit_code = 130
                warn("Command interrupted. A remotely submitted job may still be running.")
            except Exception as exc:
                exit_code = 1
                ui_error(str(exc), hint="Retry with `--log-level DEBUG` for additional diagnostics.")
            elapsed = time.monotonic() - started
            status_style = "scc.success" if exit_code == 0 else "scc.warning"
            status_icon = ICONS["success"] if exit_code == 0 else ICONS["warning"]
            console.print(f"[{status_style}]{status_icon} command finished[/] [scc.hint]in {elapsed:.1f}s · exit {exit_code}[/scc.hint]")
            console.print()
