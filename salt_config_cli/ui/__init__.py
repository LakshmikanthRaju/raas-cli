"""Interactive terminal components used by the feature-rich SCC CLI."""
from __future__ import annotations

import contextlib
import getpass
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

import click
from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .theme import ICONS, active_theme, bootstrap_theme, console, is_plain

_SERVICE = "salt-config-cli"
_RUNTIME_CONTEXT: dict[str, str] = {}


def set_runtime_context(*, profile: str | None = None, config_path: str | None = None) -> None:
    """Set process-local context automatically shown in themed command headers."""
    _RUNTIME_CONTEXT.clear()
    if profile:
        _RUNTIME_CONTEXT["profile"] = profile
    if config_path:
        _RUNTIME_CONTEXT["config_path"] = config_path



def _render(message: str) -> str:
    return message


def _plain_value(value: Any) -> str:
    """Return readable terminal text from strings or Rich renderables."""
    if isinstance(value, Text):
        return value.plain
    text = str(value)
    try:
        return Text.from_markup(text).plain
    except Exception:
        return text


def badge(text: str, style: str = "scc.badge") -> Text:
    """Return a compact status badge using a known SCC theme style.

    Callers historically used short aliases such as ``success`` and
    ``warning``. Normalize those aliases so Rich does not try to resolve an
    undefined style name at render time.
    """
    aliases = {
        "success": "scc.success",
        "warning": "scc.warning",
        "warn": "scc.warning",
        "danger": "scc.danger",
        "error": "scc.danger",
        "info": "scc.info",
    }
    resolved_style = aliases.get(style, style)
    return Text(text if is_plain() else f" {text} ", style=None if is_plain() else resolved_style)


def success(message: str, hint: str | None = None) -> None:
    if is_plain():
        click.echo(f"OK: {message}" + (f" ({hint})" if hint else ""))
        return
    line = Text.assemble((f"{ICONS['success']} ", "scc.success"), (message, "scc.value"))
    if hint:
        line.append(f"  {hint}", style="scc.hint")
    console.print(line)


def warn(message: str, hint: str | None = None) -> None:
    if is_plain():
        click.echo(f"Warning: {message}" + (f" ({hint})" if hint else ""))
        return
    line = Text.assemble((f"{ICONS['warning']} ", "scc.warning"), (message, "scc.value"))
    if hint:
        line.append(f"  {hint}", style="scc.hint")
    console.print(line)


def error(message: str, hint: str | None = None) -> None:
    if is_plain():
        click.echo(f"Error: {message}", err=True)
        if hint:
            click.echo(f"Hint: {hint}", err=True)
        return
    body = Text(message, style="scc.value")
    if hint:
        body.append(f"\n{hint}", style="scc.hint")
    console.print(Panel(body, title=f"[scc.danger]{ICONS['error']} Error[/scc.danger]", border_style="scc.danger", box=box.ROUNDED))


def info(message: str, hint: str | None = None) -> None:
    if is_plain():
        click.echo(f"Info: {message}" + (f" ({hint})" if hint else ""))
        return
    line = Text.assemble((f"{ICONS['info']} ", "scc.info"), (message, "scc.value"))
    if hint:
        line.append(f"  {hint}", style="scc.hint")
    console.print(line)


def hint(message: str) -> None:
    if is_plain():
        click.echo(f"Hint: {_plain_value(message)}")
        return
    console.print(Text.assemble((f"{ICONS['hint']} ", "scc.muted"), (message, "scc.hint")))


def banner(*, version: str | None = None, subtitle: str | None = None) -> None:
    if is_plain():
        click.echo("SALT CONFIG CLI" + (f" v{version}" if version else ""))
        if subtitle:
            click.echo(_plain_value(subtitle))
        return
    title = Text("SALT CONFIG CLI", style="scc.strong")
    if version:
        title.append(f"  v{version}", style="scc.version")
    body = [Align.center(title)]
    if subtitle:
        body.append(Align.center(Text.from_markup(subtitle, style="scc.secondary")))
    console.print(Panel(Group(*body), border_style="scc.primary", box=box.ROUNDED, padding=(1, 2)))


_LOGO = r"""
    ███████╗  ██████╗  ██████╗
    ██╔════╝ ██╔════╝ ██╔════╝
    ███████╗ ██║      ██║
    ╚════██║ ██║      ██║
    ███████║ ╚██████╗ ╚██████╗
    ╚══════╝  ╚═════╝  ╚═════╝
""".strip("\n")


def splash(*, version: str, server: str | None, username: str | None, workspace_ready: bool, profile: str | None = None) -> None:
    srv = server or "not configured"
    usr = username or "not configured"
    ws = "ready" if workspace_ready else "not initialized"
    profile_text = profile or "default"
    if is_plain():
        click.echo(f"Salt Config CLI v{version}")
        click.echo(f"server: {srv}")
        click.echo(f"user: {usr}")
        click.echo(f"profile: {profile_text}")
        click.echo(f"workspace: {ws}")
        click.echo("Quick start: scc tutorial | scc commands | scc examples | scc doctor")
        return
    logo = Text(_LOGO, style="scc.logo", justify="center")
    lines = logo.split("\n")
    if len(lines) >= 6:
        lines[2].stylize("scc.logo.secondary")
        lines[3].stylize("scc.logo.accent")
    brand = Text.assemble((f"{ICONS['sparkle']}  Salt Config CLI", "scc.primary"), (f"  v{version}", "scc.version"))
    tagline = Text("RaaS operations  •  desired state  •  fleet automation", style="scc.subtitle", justify="center")
    context = Table.grid(expand=True)
    context.add_column(justify="center")
    context.add_row(Text.from_markup(
        f"[scc.label]{ICONS['server']} server:[/scc.label] [scc.value]{srv}[/scc.value]"
        f"   ·   [scc.label]{ICONS['user']} user:[/scc.label] [scc.value]{usr}[/scc.value]"
        f"   ·   [scc.label]{ICONS['profile']} profile:[/scc.label] [scc.value]{profile_text}[/scc.value]"
        f"   ·   [scc.label]{ICONS['workspace']} workspace:[/scc.label] "
        f"[{'scc.success' if workspace_ready else 'scc.warning'}]{ws}[/]"
    ))
    shortcuts = Text.from_markup(
        f"[scc.secondary]{ICONS['rocket']} Quick start:[/scc.secondary] [scc.cmd]scc tutorial[/scc.cmd]"
        f"      [scc.secondary]{ICONS['magnify']} Browse:[/scc.secondary] [scc.cmd]scc commands[/scc.cmd]\n"
        f"[scc.secondary]{ICONS['doc']} Recipes:[/scc.secondary] [scc.cmd]scc examples[/scc.cmd]"
        f"      [scc.secondary]{ICONS['gear']} Diagnose:[/scc.secondary] [scc.cmd]scc doctor[/scc.cmd]",
        justify="center",
    )
    console.print(
        Panel(
            Group(Align.center(Group(*lines)), Align.center(brand), Align.center(tagline), Text(""), context, Text(""), shortcuts),
            border_style="scc.primary",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


def section(title: str, *, icon: str | None = None) -> None:
    if is_plain():
        click.echo(f"\n== {title} ==")
        return
    glyph = ICONS.get(icon or "", "")
    text = f"{glyph} {title}".strip()
    console.rule(f"[scc.title]{text}[/scc.title]", style="scc.primary")


def bullet_list(items: Iterable[str], *, bullet: str = "•") -> None:
    for item in items:
        if is_plain():
            click.echo(f"- {_plain_value(item)}")
        else:
            console.print(f"  [scc.accent]{bullet}[/scc.accent] [scc.value]{item}[/scc.value]")


def next_steps(items: Sequence[str], *, title: str = "Next steps") -> None:
    if is_plain():
        click.echo(f"\n{title}:")
        for idx, item in enumerate(items, 1):
            click.echo(f"  {idx}. {_plain_value(item)}")
        return
    table = Table.grid(padding=(0, 1))
    table.add_column(style="scc.accent", justify="right", no_wrap=True)
    table.add_column(style="scc.value")
    for idx, item in enumerate(items, 1):
        table.add_row(f"{idx}.", Text.from_markup(item))
    console.print(Panel(table, title=f"[scc.title]{ICONS['rocket']} {title}[/scc.title]", border_style="scc.accent", box=box.ROUNDED))


def command_header(command: str, title: str, *, description: str | None = None, icon: str = "gear", meta: Sequence[tuple[str, Any]] | None = None, mode: tuple[str, str] | None = None) -> None:
    effective_meta = list(meta or [])
    active_profile = _RUNTIME_CONTEXT.get("profile")
    if active_profile and not any(str(key).lower() == "profile" for key, _ in effective_meta):
        effective_meta.insert(0, ("Profile", active_profile))
    if is_plain():
        click.echo(f"\nscc {command} - {title}")
        if description:
            click.echo(_plain_value(description))
        if mode:
            click.echo(f"Mode: {mode[0]}")
        for key, value in effective_meta:
            click.echo(f"{key}: {_plain_value(value)}")
        return
    heading = Text()
    heading.append(f"{ICONS.get(icon, ICONS['gear'])}  ", style="scc.accent")
    heading.append(f"scc {command}", style="scc.cmd")
    if mode:
        heading.append("   ")
        heading.append(f" {mode[0]} ", style=mode[1])
    heading.append("\n")
    heading.append(title, style="scc.strong")
    if description:
        heading.append("\n")
        heading.append(description, style="scc.hint")
    content: list[Any] = [heading]
    if effective_meta:
        if console.width < 94:
            column_count = 1
        elif console.width < 142:
            column_count = min(len(effective_meta), 2)
        else:
            column_count = min(len(effective_meta), 3)
        grid = Table.grid(expand=True, padding=(0, 2))
        for _ in range(column_count): grid.add_column(ratio=1)
        cells: list[Text] = []
        for key, value in effective_meta:
            cell = Text(); cell.append(f"{key}: ", style="scc.label"); cell.append(_plain_value(value), style="scc.value"); cells.append(cell)
        for offset in range(0, len(cells), column_count):
            row = cells[offset: offset + column_count]
            while len(row) < column_count: row.append(Text(""))
            grid.add_row(*row)
        content.extend([Text(""), grid])
    console.print(Panel(Group(*content), border_style="scc.primary", box=box.ROUNDED, padding=(1, 2)))


def result_summary(title: str, *, status: str = "success", message: str | None = None, metrics: Sequence[tuple[int | str, str, str]] | None = None, details: Mapping[str, Any] | Sequence[tuple[Any, Any]] | None = None) -> None:
    if is_plain():
        click.echo(f"\n{status.upper()}: {title}")
        if message: click.echo(_plain_value(message))
        if metrics: click.echo(" | ".join(f"{value} {label}" for value, label, _ in metrics))
        if details:
            rows = details.items() if isinstance(details, Mapping) else details
            for key, value in rows: click.echo(f"{key}: {_plain_value(value)}")
        return
    status_map = {"success": (ICONS["success"], "scc.success"), "warning": (ICONS["warning"], "scc.warning"), "danger": (ICONS["error"], "scc.danger"), "info": (ICONS["info"], "scc.info")}
    glyph, style = status_map.get(status, status_map["info"])
    heading = Text.assemble((f"{glyph}  ", style), (title, f"{style} bold"))
    parts: list[Any] = [heading]
    if message: parts.extend([Text(""), Text(message, style="scc.value")])
    if metrics:
        line = Text()
        for idx, (value, label, kind) in enumerate(metrics):
            if idx: line.append("  ")
            line.append(f" {value} {label} ", style=f"scc.metric.{kind}" if kind in {"primary", "secondary", "accent", "success", "warning", "danger", "info"} else "reverse")
        parts.extend([Text(""), line])
    if details:
        grid = Table.grid(padding=(0, 2)); grid.add_column(style="scc.label", no_wrap=True); grid.add_column(style="scc.value", overflow="fold")
        rows = details.items() if isinstance(details, Mapping) else details
        for key, value in rows: grid.add_row(str(key), value if hasattr(value, "__rich_console__") else str(value))
        parts.extend([Text(""), grid])
    console.print(Panel(Group(*parts), border_style=style, box=box.ROUNDED, padding=(1, 2)))


def empty_state(title: str, message: str, *, icon: str = "magnify", actions: Sequence[str] | None = None) -> None:
    if is_plain():
        click.echo(f"\n{title}: {message}")
        for idx, action in enumerate(actions or [], 1): click.echo(f"  {idx}. {_plain_value(action)}")
        return
    body: list[Any] = [Text(message, style="scc.value")]
    if actions:
        table = Table.grid(padding=(0, 1)); table.add_column(style="scc.accent", justify="right", no_wrap=True); table.add_column(style="scc.cmd")
        for idx, action in enumerate(actions, 1): table.add_row(f"{idx}.", action)
        body.extend([Text(""), table])
    console.print(Panel(Group(*body), title=f"[scc.title]{ICONS.get(icon, '')} {title}[/scc.title]", border_style="scc.secondary", box=box.ROUNDED, padding=(1, 2)))


def _table_cell(value: Any) -> Any:
    if hasattr(value, "__rich_console__"):
        return value
    if isinstance(value, str):
        try:
            return Text.from_markup(value)
        except Exception:
            return Text(value)
    return Text(str(value))


def data_table(title: str, columns: Sequence[tuple[str, str]], rows: Sequence[Sequence[Any]], *, icon: str = "doc", border_style: str = "scc.primary", caption: str | None = None) -> None:
    if is_plain():
        click.echo(f"\n{title}")
        headers = [name for name, _ in columns]
        plain_rows = [[_plain_value(item) for item in row] for row in rows]
        widths = [len(header) for header in headers]
        for row in plain_rows:
            for idx, value in enumerate(row[:len(widths)]): widths[idx] = max(widths[idx], len(value))
        click.echo("  ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers)))
        click.echo("  ".join("-" * width for width in widths))
        for row in plain_rows: click.echo("  ".join((row[idx] if idx < len(row) else "").ljust(widths[idx]) for idx in range(len(widths))))
        if caption: click.echo(_plain_value(caption))
        return

    # Wide inventory tables become unreadable when every field is squeezed into
    # a narrow terminal. Switch to responsive record cards instead of wrapping
    # words one character at a time. This is used by profiles, jobs, pillars and
    # other dense operational results.
    card_breakpoint = max(104, 20 * len(columns))
    if len(columns) >= 5 and console.width < card_breakpoint:
        cards: list[Any] = []
        for index, row in enumerate(rows, 1):
            values = list(row) + [""] * max(0, len(columns) - len(row))
            first_label = columns[0][0] if columns else "Record"
            first_value = _plain_value(values[0]) if values else str(index)
            grid = Table.grid(expand=True, padding=(0, 1))
            grid.add_column(style="scc.label", no_wrap=True, width=min(22, max(10, max((len(name) for name, _ in columns[1:]), default=10))))
            grid.add_column(style="scc.value", overflow="fold", ratio=1)
            for (name, _style), value in zip(columns[1:], values[1:]):
                grid.add_row(name, _table_cell(value))
            cards.append(
                Panel(
                    grid,
                    title=Text.assemble((f"{first_label}: ", "scc.label"), (first_value, "scc.strong")),
                    border_style="scc.secondary",
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
        content: list[Any] = []
        for index, card in enumerate(cards):
            if index:
                content.append(Text(""))
            content.append(card)
        if not content:
            content.append(Text("No records", style="scc.muted"))
        panel = Panel(
            Group(*content),
            title=f"[scc.title]{ICONS.get(icon, '')} {title}[/scc.title]",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(0, 1),
        )
        if caption:
            panel.subtitle = Text(_plain_value(caption), style="scc.hint")
        console.print(panel)
        return

    table = Table(box=box.SIMPLE, expand=True, header_style="scc.secondary", padding=(0, 1), collapse_padding=True)
    for name, style in columns:
        table.add_column(name, style=style, overflow="fold", no_wrap=name in {"Status", "Count", "Type"})
    for row in rows:
        table.add_row(*[_table_cell(item) for item in row])
    if caption:
        table.caption = caption
        table.caption_style = "scc.hint"
    console.print(Panel(table, title=f"[scc.title]{ICONS.get(icon, '')} {title}[/scc.title]", border_style=border_style, box=box.ROUNDED, padding=(0, 1)))


def kv_table(title: str, values: Mapping[str, Any] | Sequence[tuple[Any, Any]]) -> None:
    rows = list(values.items() if isinstance(values, Mapping) else values)
    for row in rows:
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or len(row) != 2: raise ValueError("kv_table rows must be (key, value) pairs")
    if is_plain():
        click.echo(f"\n{title}")
        width = max((len(str(key)) for key, _ in rows), default=0)
        for key, value in rows: click.echo(f"{str(key).ljust(width)} : {_plain_value(value)}")
        return
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1)); table.add_column(style="scc.label", no_wrap=True); table.add_column(style="scc.value", overflow="fold")
    for key, value in rows: table.add_row(str(key), value if hasattr(value, "__rich_console__") else str(value))
    console.print(Panel(table, title=f"[scc.title]{title}[/scc.title]", border_style="scc.primary", box=box.ROUNDED))


def summary_pills(items: Sequence[tuple[int, str, str]]) -> None:
    if is_plain():
        click.echo(" | ".join(f"{count} {label}" for count, label, _ in items)); return
    line = Text()
    for idx, (count, label, kind) in enumerate(items):
        if idx: line.append("  ")
        line.append(f" {count} {label} ", style=f"scc.metric.{kind}" if kind in {"primary", "secondary", "accent", "success", "warning", "danger", "info"} else "reverse")
    console.print(line)


def tree_panel(title: str, children: Sequence[Any], *, icon: str = "folder") -> None:
    if is_plain():
        click.echo(f"\n{title}")
        for child in children:
            if isinstance(child, tuple):
                label, detail = child[0], child[1] if len(child) > 1 else ""
                click.echo(f"- {label}" + (f"  {detail}" if detail else ""))
            else: click.echo(f"- {child}")
        return
    tree = Text()
    for idx, child in enumerate(children):
        if isinstance(child, tuple): label, detail = child[0], child[1] if len(child) > 1 else ""
        else: label, detail = str(child), ""
        branch = "└──" if idx == len(children) - 1 else "├──"; tree.append(f"{branch} ", style="scc.muted"); tree.append(str(label), style="scc.value")
        if detail: tree.append(f"  {detail}", style="scc.hint")
        tree.append("\n")
    console.print(Panel(tree, title=f"[scc.secondary]{ICONS.get(icon, '')} {title}[/scc.secondary]", border_style="scc.primary", box=box.ROUNDED))


def mask(value: str | None, *, visible: int = 3) -> str:
    if not value:
        return ""
    text = str(value)
    if len(text) <= visible * 2:
        return "*" * len(text)
    return text[:visible] + "…" + text[-visible:]


def mask_url(value: str | None) -> str:
    if not value:
        return ""
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
    except Exception:
        return re.sub(r"//[^/@]+@", "//***@", value)


def prompt_password(prompt: str = "Password") -> str:
    return getpass.getpass(f"{prompt}: ")


def _read_password_file(path: str) -> str:
    p = Path(path).expanduser()
    if not p.is_file():
        raise click.ClickException(f"Password file does not exist: {p}")
    return p.read_text(encoding="utf-8").strip("\r\n")


def resolve_password(*, cli_password: str | None, password_stdin: bool, password_file: str | None,
                     password_prompt: bool, server: str | None, username: str | None,
                     existing: str | None = None) -> tuple[str | None, str]:
    if password_stdin:
        return sys.stdin.readline().rstrip("\r\n"), "stdin"
    if password_file:
        return _read_password_file(password_file), "file"
    if password_prompt:
        return prompt_password(), "prompt"
    if os.getenv("SCC_PASSWORD"):
        return os.environ["SCC_PASSWORD"], "environment"
    stored = keychain_get(server, username)
    if stored:
        return stored, "keychain"
    if cli_password:
        return cli_password, "cli"
    if existing:
        return existing, "config"
    return None, "none"


def keychain_available() -> bool:
    try:
        import keyring
        backend = keyring.get_keyring()
        return backend.priority > 0
    except Exception:
        return False


def _key(server: str | None, username: str | None) -> str:
    return f"{mask_url(server) or 'default'}::{username or 'default'}"


def keychain_get(server: str | None, username: str | None) -> str | None:
    if not keychain_available():
        return None
    try:
        import keyring
        return keyring.get_password(_SERVICE, _key(server, username))
    except Exception:
        return None


def keychain_set(server: str | None, username: str | None, password: str) -> bool:
    if not keychain_available():
        return False
    try:
        import keyring
        keyring.set_password(_SERVICE, _key(server, username), password)
        return True
    except Exception:
        return False


def keychain_delete(server: str | None, username: str | None) -> bool:
    if not keychain_available():
        return False
    try:
        import keyring
        keyring.delete_password(_SERVICE, _key(server, username))
        return True
    except Exception:
        return False


def warn_cli_password(option: str) -> None:
    warn(
        f"{option} can expose a secret in shell history and process listings.",
        hint="Prefer `scc login`, --password-stdin, --password-file, or --password-prompt.",
    )


@contextlib.contextmanager
def spinner(message: str):
    if is_plain():
        click.echo(_plain_value(message))
        yield
        return
    with console.status(f"[scc.info]{message}[/scc.info]", spinner="dots"):
        yield


def confirm_destructive(*, action: str, targets_summary: str, typed_phrase: str,
                        auto_approve: bool = False) -> bool:
    if auto_approve:
        return True
    warn(f"About to {action}", hint=targets_summary)
    if not sys.stdin.isatty():
        return False
    entered = click.prompt(f"Type '{typed_phrase}' to continue", default="", show_default=False)
    return entered.strip().lower() == typed_phrase.lower()


class RowTracker:
    """Small live table used for apply, job and minion progress rendering."""
    def __init__(self, *, columns: Sequence[str], title: str = "Progress", border_style: str = "scc.primary"):
        self.columns = tuple(columns)
        self.title = title
        self.border_style = border_style
        self.rows: dict[str, list[str]] = {}
        self.footer_text = ""
        self._live: Live | None = None

    def _render(self) -> Panel:
        table = Table(expand=True, box=box.SIMPLE, header_style="scc.secondary")
        for column in self.columns:
            table.add_column(column, overflow="fold")
        for key, values in self.rows.items():
            rendered = [key] + list(values)
            while len(rendered) < len(self.columns):
                rendered.append("")
            table.add_row(*rendered[: len(self.columns)])
        group: list[Any] = [table]
        if self.footer_text:
            group += [Text(""), Text(self.footer_text, style="scc.hint")]
        return Panel(Group(*group), title=f"[scc.title]{self.title}[/scc.title]", border_style=self.border_style, box=box.ROUNDED)

    def __enter__(self):
        if is_plain():
            click.echo(f"{self.title}:")
            return self
        self._live = Live(self._render(), console=console, refresh_per_second=8, transient=False)
        self._live.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._live:
            self._live.update(self._render(), refresh=True)
            self._live.__exit__(exc_type, exc, tb)
        elif is_plain() and self.footer_text:
            click.echo(self.footer_text)

    def _refresh(self):
        if self._live:
            self._live.update(self._render(), refresh=True)

    def add(self, key: str, *, status: str = "pending", detail: str = "", **kwargs: Any) -> None:
        values = [self._status(status), detail]
        for name in self.columns[3:]:
            values.append(str(kwargs.get(name.lower(), kwargs.get(name, ""))))
        self.rows[str(key)] = values
        if is_plain():
            click.echo(f"  {key}: {_plain_value(values[0])}" + (f" - {detail}" if detail else ""))
        self._refresh()

    def set(self, key: str, *, status: str | None = None, detail: str | None = None, **kwargs: Any) -> None:
        current = self.rows.setdefault(str(key), [self._status("pending"), ""])
        if status is not None:
            current[0] = self._status(status)
        if detail is not None:
            if len(current) < 2:
                current.append(detail)
            else:
                current[1] = detail
        for idx, name in enumerate(self.columns[3:], start=2):
            while len(current) <= idx:
                current.append("")
            if name.lower() in kwargs or name in kwargs:
                current[idx] = str(kwargs.get(name.lower(), kwargs.get(name, "")))
        if is_plain():
            click.echo(f"  {key}: {_plain_value(current[0])}" + (f" - {current[1]}" if len(current) > 1 and current[1] else ""))
        self._refresh()

    update = set

    def footer(self, text: str) -> None:
        self.footer_text = text
        self._refresh()

    @staticmethod
    def _status(value: str) -> str:
        if is_plain():
            return value.lower()
        states = {
            "ok": f"[scc.success]{ICONS['success']} ok[/scc.success]",
            "success": f"[scc.success]{ICONS['success']} success[/scc.success]",
            "fail": f"[scc.danger]{ICONS['error']} failed[/scc.danger]",
            "failed": f"[scc.danger]{ICONS['error']} failed[/scc.danger]",
            "active": f"[scc.info]{ICONS['running']} running[/scc.info]",
            "running": f"[scc.info]{ICONS['running']} running[/scc.info]",
            "pending": "[scc.muted]pending[/scc.muted]",
            "skip": "[scc.muted]skipped[/scc.muted]",
        }
        return states.get(value.lower(), value)


def _help_program(ctx: click.Context) -> str:
    """Return a user-facing command path that always starts with ``scc``."""
    path = (ctx.command_path or ctx.info_name or "scc").strip()
    parts = path.split()
    if not parts:
        return "scc"
    if parts[0] in {"python", "python3"}:
        if len(parts) >= 3 and parts[1] == "-m":
            parts = ["scc", *parts[3:]]
        else:
            parts[0] = "scc"
    elif parts[0] == "cli" or parts[0].endswith(".py"):
        parts[0] = "scc"
    elif parts[0] not in {"scc", "salt-config", "raas"}:
        parts.insert(0, "scc")
    return " ".join(parts)


def _help_console(ctx: click.Context, stream) -> Console:
    """Create a console used to capture Rich help for Click.

    In a real terminal this retains SCC colours. In pipes and tests it emits the
    same panels and tables without ANSI escape sequences.
    """
    width = max(76, min(ctx.terminal_width or console.width or 110, 140))
    force_terminal = bool(ctx.color is not False and getattr(sys.stdout, "isatty", lambda: False)())
    return Console(
        file=stream,
        theme=active_theme(),
        highlight=False,
        soft_wrap=False,
        width=width,
        force_terminal=force_terminal,
        color_system="truecolor" if force_terminal else None,
    )


def _command_description(command: click.Command) -> tuple[str, str]:
    raw = (command.help or command.get_short_help_str(limit=120) or "").replace("\b", "").strip()
    if not raw:
        return command.name or "Command", ""
    before_examples = raw.split("Examples:", 1)[0].strip()
    paragraphs = [" ".join(part.split()) for part in before_examples.split("\n\n") if part.strip()]
    title = paragraphs[0] if paragraphs else command.get_short_help_str(limit=120)
    detail = "\n\n".join(paragraphs[1:])
    return title, detail


def _extract_examples(command: click.Command) -> list[str]:
    raw = (command.help or "").replace("\b", "")
    if "Examples:" not in raw:
        return []
    block = raw.split("Examples:", 1)[1]
    examples: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("$"):
            examples.append(stripped[1:].strip())
        elif stripped.startswith("scc "):
            examples.append(stripped)
        elif stripped.startswith(("salt-config ", "raas ")):
            examples.append(stripped)
    return examples[:8]


def _option_category(param: click.Parameter) -> str:
    name = (getattr(param, "name", "") or "").replace("_", "-")
    if isinstance(param, click.Argument):
        return "Arguments"
    if name in {"server", "username", "password", "password-stdin", "password-file", "password-prompt", "csp-token", "config", "insecure"}:
        return "Connection & authentication"
    if name in {"json", "yaml", "raw", "output", "output-file", "no-color", "log-level", "flat", "theme"}:
        return "Output & display"
    if name in {"yes", "force", "no-test", "test", "dry-run", "auto-approve", "destroy"}:
        return "Safety & execution"
    if any(token in name for token in ("target", "minion", "master", "env", "pillar")):
        return "Targeting & scope"
    return "Command options"


def _parameter_usage(param: click.Parameter) -> str:
    if isinstance(param, click.Argument):
        name = (param.human_readable_name or param.name or "ARG").upper()
        return f"<{name}>" if param.required else f"[{name}]"
    return ""


def _safety_message(command_name: str) -> str | None:
    mutating = {
        "apply", "destroy", "remediate", "run", "exec", "job-run", "job-delete",
        "job-create", "upload", "upload-module", "upload-pillar", "pillar-assign",
        "pillar-refresh", "target-group-create", "edit", "import", "rpc",
    }
    if command_name not in mutating:
        return None
    if command_name == "run":
        return "State execution is dry-run by default. Use --no-test to apply changes only after reviewing the proposal."
    if command_name == "exec":
        return "Read-only Salt functions run directly. Potentially mutating functions require confirmation."
    if command_name == "rpc":
        return "Raw RPC calls can change RaaS or minion state. Prefer a purpose-built SCC command when available."
    return "This command can change remote state. Review the target and options before confirming."


def _related_commands(command_name: str) -> list[str]:
    related = {
        "configure": ["profile", "config", "status"],
        "profile": ["configure", "config", "status"],
        "config": ["profile", "configure", "doctor"],
        "theme": ["config", "profile", "help"],
        "status": ["profile", "doctor", "system-info"],
        "connect": ["status", "doctor", "list"],
        "list": ["fs-list", "target-group-list", "pillar-list"],
        "fs-list": ["download", "upload", "edit"],
        "upload": ["fs-list", "download", "run"],
        "run": ["job-create", "job-results", "exec"],
        "exec": ["list", "target-group-list", "job-results"],
        "job-create": ["job-list", "job-run", "job-results"],
        "job-run": ["job-status", "job-results", "job-list"],
        "drift": ["plan", "remediate", "show"],
        "remediate": ["drift", "plan", "apply"],
        "pillar-list": ["upload-pillar", "pillar-assign", "pillar-refresh"],
        "target-group-list": ["target-group-create", "pillar-assign", "exec"],
    }
    return related.get(command_name, [])


def render_rich_help(command: click.Command, ctx: click.Context) -> str:
    """Render group or command help using the selected SCC visual language."""
    import io

    root = ctx.find_root()
    params = getattr(root, "params", {}) or {}
    bootstrap_theme(
        cli_theme=params.get("theme_name"),
        config_path=params.get("global_config_path"),
        profile_name=params.get("profile_name"),
    )
    if is_plain():
        formatter = ctx.make_formatter()
        command.format_help(ctx, formatter)
        return formatter.getvalue()

    stream = io.StringIO()
    help_console = _help_console(ctx, stream)
    program = _help_program(ctx)

    if isinstance(command, click.Group):
        is_root = program in {"scc", "salt-config", "raas"}
        title = Text("SALT CONFIG CLI", style="scc.strong")
        try:
            from salt_config_cli import __version__
            title.append(f"  v{__version__}", style="scc.version")
        except Exception:
            pass
        if is_root:
            intro_text = "Interactive RaaS operations, Salt execution, file-server management, saved jobs and desired-state workflows."
        else:
            headline, detail = _command_description(command)
            intro_text = headline + (f"\n{detail}" if detail else "")
        intro = Text(intro_text, style="scc.value", justify="center")
        help_console.print(
            Panel(
                Group(Align.center(title), Text(""), intro),
                border_style="scc.primary",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

        usage_suffix = "[GLOBAL OPTIONS] <COMMAND> [ARGS]" if is_root else "<COMMAND> [ARGS]"
        usage = Text.assemble(
            (f"{ICONS['rocket']}  Usage  ", "scc.secondary"),
            (f"{program} ", "scc.cmd"),
            (usage_suffix, "scc.value"),
        )
        help_console.print(Panel(usage, border_style="scc.accent", box=box.ROUNDED, padding=(0, 2)))

        if is_root:
            rows: dict[str, list[tuple[str, str]]] = {name: [] for name in RichGroup.CATEGORY_ORDER}
            for name in command.list_commands(ctx):
                subcommand = command.get_command(ctx, name)
                if subcommand is None or subcommand.hidden:
                    continue
                rows.setdefault(_command_category(name), []).append((name, subcommand.get_short_help_str(limit=88)))

            category_icons = {
                "Getting started": "rocket", "Configuration": "workspace", "Operations": "gear",
                "Jobs": "job", "File server": "folder", "Targeting & pillar": "target",
                "Desired state": "shield", "Diagnostics": "magnify", "Discovery": "sparkle", "Other": "doc",
            }
            for category in RichGroup.CATEGORY_ORDER:
                entries = rows.get(category) or []
                if not entries:
                    continue
                table = Table(box=box.SIMPLE, show_header=False, expand=True, padding=(0, 2))
                table.add_column("Command", style="scc.cmd", no_wrap=True, width=29)
                table.add_column("Description", style="scc.value", overflow="fold")
                for name, description in entries:
                    table.add_row(f"scc {name}", Text(description or "", style="scc.value"))
                icon = ICONS.get(category_icons.get(category, "doc"), "")
                help_console.print(
                    Panel(
                        table,
                        title=f"[scc.title]{icon} {category}[/scc.title]",
                        border_style="scc.primary",
                        box=box.ROUNDED,
                        padding=(0, 1),
                    )
                )
        else:
            table = Table(box=box.SIMPLE, show_header=False, expand=True, padding=(0, 2))
            table.add_column("Command", style="scc.cmd", no_wrap=True, width=34)
            table.add_column("Description", style="scc.value", overflow="fold")
            for name in command.list_commands(ctx):
                subcommand = command.get_command(ctx, name)
                if subcommand is None or subcommand.hidden:
                    continue
                table.add_row(f"{program} {name}", subcommand.get_short_help_str(limit=92) or "")
            group_icon = "profile" if command.name == "profile" else "config" if command.name == "config" else "theme" if command.name == "theme" else "gear"
            group_title = f"{(command.name or 'Group').replace('-', ' ').title()} commands"
            help_console.print(
                Panel(
                    table,
                    title=f"[scc.title]{ICONS.get(group_icon, ICONS['gear'])} {group_title}[/scc.title]",
                    border_style="scc.primary",
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )

        options = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=True)
        options.add_column(style="scc.cmd", no_wrap=True, width=22)
        options.add_column(style="scc.value", overflow="fold")
        if is_root:
            options.add_row("--profile NAME", "Use a named connection profile for this invocation.")
            options.add_row("--config-file PATH", "Use a specific profile configuration file.")
            options.add_row("--theme NAME", "Use a professional theme or plain output for this invocation.")
            options.add_row("--version", "Show the installed SCC version.")
            options.add_row("--help", "Show this themed command reference.")
            options_title = "Global options"
        else:
            options.add_row("scc --profile NAME …", "Select a profile before the group command.")
            options.add_row("scc --config-file PATH …", "Select another config file before the group command.")
            options.add_row("--help", "Show this themed group reference.")
            options_title = "Inherited options"
        help_console.print(Panel(options, title=f"[scc.title]{options_title}[/scc.title]", border_style="scc.secondary", box=box.ROUNDED))

        next_table = Table.grid(padding=(0, 1))
        next_table.add_column(style="scc.accent", justify="right", no_wrap=True)
        next_table.add_column(style="scc.value")
        if command.name == "profile":
            next_table.add_row("1.", Text.from_markup("List connections with [scc.cmd]scc profile list[/scc.cmd]."))
            next_table.add_row("2.", Text.from_markup("Create or edit one with [scc.cmd]scc configure --name <name>[/scc.cmd]."))
            next_table.add_row("3.", Text.from_markup("Activate it with [scc.cmd]scc profile use <name>[/scc.cmd]."))
        elif command.name == "config":
            next_table.add_row("1.", Text.from_markup("Inspect values with [scc.cmd]scc config show[/scc.cmd]."))
            next_table.add_row("2.", Text.from_markup("Validate profiles with [scc.cmd]scc config validate[/scc.cmd]."))
            next_table.add_row("3.", Text.from_markup("Review overrides with [scc.cmd]scc config env[/scc.cmd]."))
        elif command.name == "theme":
            next_table.add_row("1.", Text.from_markup("Browse presets with [scc.cmd]scc theme list[/scc.cmd]."))
            next_table.add_row("2.", Text.from_markup("Preview one with [scc.cmd]scc theme preview enterprise[/scc.cmd]."))
            next_table.add_row("3.", Text.from_markup("Use normal output with [scc.cmd]scc theme disable[/scc.cmd]."))
        else:
            next_table.add_row("1.", Text.from_markup("Create or choose a connection with [scc.cmd]scc configure[/scc.cmd] and [scc.cmd]scc profile list[/scc.cmd]."))
            next_table.add_row("2.", Text.from_markup("Find a command using [scc.cmd]scc search <keyword>[/scc.cmd]."))
            next_table.add_row("3.", Text.from_markup("Open focused help using [scc.cmd]scc help <command>[/scc.cmd]."))
        help_console.print(Panel(next_table, title=f"[scc.title]{ICONS['sparkle']} Start here[/scc.title]", border_style="scc.accent", box=box.ROUNDED))
    else:
        command_name = command.name or program.split()[-1]
        headline, detail = _command_description(command)
        header = Text()
        header.append(f"{ICONS['gear']}  {program}", style="scc.primary")
        header.append("\n")
        header.append(headline, style="scc.strong")
        if detail:
            header.append("\n\n")
            header.append(detail, style="scc.value")
        help_console.print(Panel(header, border_style="scc.primary", box=box.ROUNDED, padding=(1, 2)))

        args = [_parameter_usage(p) for p in command.params if isinstance(p, click.Argument)]
        args = [a for a in args if a]
        syntax = f"{program} [OPTIONS]" + (" " + " ".join(args) if args else "")
        help_console.print(
            Panel(
                Text.assemble((f"{ICONS['rocket']}  Syntax  ", "scc.secondary"), (syntax, "scc.cmd")),
                border_style="scc.accent",
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )

        categorized: dict[str, list[tuple[str, str, str]]] = {}
        for param in command.params:
            if isinstance(param, click.Argument):
                label = _parameter_usage(param)
                description = getattr(param, "help", None) or f"Value for {param.human_readable_name}."
                requirement = "Required." if param.required else "Optional."
                categorized.setdefault("Arguments", []).append((label, f"{description} {requirement}", ""))
                continue
            record = param.get_help_record(ctx)
            if record is None:
                continue
            opts, description = record
            description = re.sub(r"\s*\[default:[^]]+\]", "", description or "").strip()
            default = ""
            param_default = getattr(param, "default", None)
            if param_default not in (None, False, ()) and not getattr(param, "hide_input", False):
                if getattr(param, "is_bool_flag", False) and getattr(param, "secondary_opts", None):
                    selected = (param.opts[0] if param_default else param.secondary_opts[0]).lstrip("-")
                    default = f"[default: {selected}]"
                else:
                    default = f"[default: {param_default}]"
            categorized.setdefault(_option_category(param), []).append((opts, description, default))

        category_order = ["Arguments", "Command options", "Targeting & scope", "Safety & execution", "Output & display", "Connection & authentication"]
        for category in category_order:
            entries = categorized.get(category) or []
            if not entries:
                continue
            table = Table(box=box.SIMPLE, show_header=False, expand=True, padding=(0, 2))
            table.add_column("Option", style="scc.cmd", no_wrap=False, width=30, ratio=2)
            table.add_column("Description", style="scc.value", overflow="fold", ratio=3)
            for option, description, default in entries:
                option_text = Text(option, style="scc.cmd")
                if default:
                    option_text.append("\n")
                    option_text.append(default, style="scc.hint")
                table.add_row(option_text, Text(description, style="scc.value"))
            help_console.print(Panel(table, title=f"[scc.title]{category}[/scc.title]", border_style="scc.primary", box=box.ROUNDED, padding=(0, 1)))

        safety = _safety_message(command_name)
        if safety:
            help_console.print(
                Panel(
                    Text(safety, style="scc.value"),
                    title=f"[scc.warning]{ICONS['shield']} Safety[/scc.warning]",
                    border_style="scc.warning",
                    box=box.ROUNDED,
                )
            )

        examples = _extract_examples(command)
        if examples:
            body = Text()
            for idx, example in enumerate(examples):
                if idx:
                    body.append("\n")
                body.append("$ ", style="scc.muted")
                body.append(example, style="scc.cmd")
            help_console.print(Panel(body, title=f"[scc.title]{ICONS['doc']} Examples[/scc.title]", border_style="scc.accent", box=box.ROUNDED, padding=(1, 2)))

        related = _related_commands(command_name)
        if related:
            line = Text("  ")
            for idx, name in enumerate(related):
                if idx:
                    line.append("    ")
                line.append(f"scc {name}", style="scc.cmd")
            help_console.print(Panel(line, title=f"[scc.title]{ICONS['arrow']} Related commands[/scc.title]", border_style="scc.secondary", box=box.ROUNDED))

    return stream.getvalue().rstrip() + "\n"


class RichCommand(click.Command):
    """Click command whose ``--help`` output uses the SCC Rich theme."""

    def get_help(self, ctx: click.Context) -> str:
        return render_rich_help(self, ctx)


class RichGroup(click.Group):
    """Click group with category-aware, fully themed help."""

    command_class = RichCommand
    group_class = type

    CATEGORY_ORDER = [
        "Getting started", "Configuration", "Operations", "Jobs", "File server",
        "Targeting & pillar", "Desired state", "Diagnostics", "Discovery", "Other",
    ]

    def get_help(self, ctx: click.Context) -> str:
        return render_rich_help(self, ctx)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        # Retained for compatibility with tools that call Click's formatter
        # directly instead of ``get_help``.
        rows: dict[str, list[tuple[str, str]]] = {name: [] for name in self.CATEGORY_ORDER}
        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is None or cmd.hidden:
                continue
            category = _command_category(name)
            rows.setdefault(category, []).append((name, cmd.get_short_help_str(limit=72)))
        for category in self.CATEGORY_ORDER:
            commands = rows.get(category) or []
            if commands:
                with formatter.section(category):
                    formatter.write_dl(commands)

def _command_category(name: str) -> str:
    if name in {"configure", "configure-git", "profile", "config", "theme", "repo"}:
        return "Configuration"
    if name in {"init", "connect", "login", "status", "tutorial", "shell", "system-info", "workflow", "deploy"}:
        return "Getting started"
    if name in {"show", "validate", "plan", "apply", "destroy", "refresh"}:
        return "Configuration"
    if name in {"exec", "run", "list"}:
        return "Operations"
    if name.startswith("job-"):
        return "Jobs"
    if name in {"fs-list", "upload", "download", "edit", "import", "upload-module"}:
        return "File server"
    if name.startswith("target-") or name.startswith("pillar-") or name == "upload-pillar":
        return "Targeting & pillar"
    if name in {"drift", "remediate"}:
        return "Desired state"
    if name in {"doctor", "clear-cache", "disconnect", "logout"}:
        return "Diagnostics"
    if name in {"commands", "search", "examples", "help", "completion"}:
        return "Discovery"
    return "Other"


def install_error_handler() -> None:
    """Install concise top-level exception rendering unless debug mode is enabled."""
    # Click already owns normal command errors.  We only make Rich traceback opt-in.
    if os.getenv("SCC_DEBUG"):
        try:
            from rich.traceback import install
            install(console=console, show_locals=False)
        except Exception:
            pass
