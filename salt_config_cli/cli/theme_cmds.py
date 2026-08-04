"""Professional theme selection and persistence commands."""
from __future__ import annotations

import json
import os
from typing import Optional

import click
from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from salt_config_cli.core.config import ConnectionProfile, ProfileConfigStore, discover_config_path
from salt_config_cli.ui import (
    ICONS,
    RichGroup,
    command_header,
    data_table,
    next_steps,
    result_summary,
)
from salt_config_cli.ui.theme import (
    DEFAULT_THEME,
    PRESETS,
    active_theme_name,
    configure_theme,
    normalize_theme_name,
    theme_rows,
    console,
)


def _root_value(ctx: click.Context, key: str, default=None):
    root = ctx.find_root()
    return (root.obj or {}).get(key, default)


def _store(ctx: click.Context) -> ProfileConfigStore:
    return ProfileConfigStore(discover_config_path(_root_value(ctx, "config_path")))


def _selected_profile(ctx: click.Context) -> str:
    store = _store(ctx)
    config = store.load()
    return _root_value(ctx, "profile") or os.getenv("SCC_PROFILE") or config.default_profile


def _source(ctx: click.Context, effective: str) -> tuple[str, str | None]:
    if _root_value(ctx, "theme_explicit"):
        return "command line", None
    if os.getenv("SCC_THEME"):
        return "environment (SCC_THEME)", None
    store = _store(ctx)
    config = store.load()
    profile_name = _selected_profile(ctx)
    profile = config.profiles.get(profile_name)
    if profile and profile.theme:
        return f"profile '{profile_name}'", profile_name
    if config.theme:
        return "global configuration", None
    return "built-in default", None


def _save_theme(ctx: click.Context, name: str, profile_name: Optional[str]) -> None:
    store = _store(ctx)
    config = store.load()
    if profile_name:
        profile = config.profiles.get(profile_name)
        if profile is None:
            available = ", ".join(sorted(config.profiles)) or "none"
            raise click.ClickException(
                f"Profile '{profile_name}' does not exist. Available profiles: {available}"
            )
        config.profiles[profile_name] = profile.model_copy(update={"theme": name})
    else:
        config.theme = name
    store.save(config)


def _preview_card(name: str) -> None:
    preset = PRESETS[name]
    table = Table(box=box.SIMPLE, show_header=True, header_style="scc.table.header", expand=True)
    table.add_column("State")
    table.add_column("Example")
    table.add_row("Command", Text("scc exec test.ping --target 'web-*'", style="scc.cmd"))
    table.add_row("Success", Text(f"{ICONS['success']} 18 minions responded", style="scc.success"))
    table.add_row("Warning", Text(f"{ICONS['warning']} 2 minions are offline", style="scc.warning"))
    table.add_row("Error", Text(f"{ICONS['error']} Authentication failed", style="scc.danger"))
    console.print(
        Panel(
            table,
            title=f"[scc.title]{preset.label}[/scc.title]",
            subtitle=f"[scc.hint]{preset.description}[/scc.hint]",
            border_style="scc.primary",
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )


@click.group("theme", cls=RichGroup, invoke_without_command=True)
@click.pass_context
def theme_group(ctx: click.Context) -> None:
    """Choose, preview or disable SCC terminal themes."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help(), nl=False)


@theme_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@click.pass_context
def list_themes(ctx: click.Context, as_json: bool) -> None:
    """List professional themes and identify the active selection."""
    active = active_theme_name()
    if as_json:
        click.echo(json.dumps({
            "active": active,
            "themes": [
                {"name": name, "label": label, "description": description, "active": name == active}
                for name, label, description in theme_rows()
            ],
        }, indent=2))
        return
    command_header(
        "theme list",
        "Available terminal themes",
        description="Themes change presentation only; JSON and YAML automation output remain undecorated.",
        icon="theme",
        meta=[("Active", active), ("Available", len(PRESETS))],
    )
    rows = []
    for name, label, description in theme_rows():
        status = Text("active", style="scc.success") if name == active else Text("available", style="scc.muted")
        rows.append([name, label, description, status])
    data_table(
        "Professional themes",
        [("Name", "scc.cmd"), ("Display", "scc.strong"), ("Purpose", "scc.value"), ("Status", "scc.value")],
        rows,
        icon="theme",
    )
    next_steps([
        "Preview one: `scc theme preview enterprise`.",
        "Select globally: `scc theme use graphite`.",
        "Disable enhanced presentation: `scc theme disable`.",
    ])


@theme_group.command("current")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@click.pass_context
def current_theme(ctx: click.Context, as_json: bool) -> None:
    """Show the effective theme and where it was selected."""
    effective = active_theme_name()
    source, profile = _source(ctx, effective)
    payload = {
        "theme": effective,
        "label": PRESETS[effective].label,
        "plain": PRESETS[effective].plain,
        "source": source,
        "profile": profile,
        "config_path": str(_store(ctx).path),
    }
    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return
    result_summary(
        f"Theme: {PRESETS[effective].label}",
        status="info",
        message=PRESETS[effective].description,
        details=[("Theme ID", effective), ("Source", source), ("Config file", _store(ctx).path)],
    )


@theme_group.command("preview")
@click.argument("name", required=False)
@click.option("--all", "preview_all", is_flag=True, help="Preview every professional preset.")
@click.pass_context
def preview_theme(ctx: click.Context, name: Optional[str], preview_all: bool) -> None:
    """Preview one theme, or all themes, without saving the selection."""
    original = active_theme_name()
    names = list(PRESETS) if preview_all or not name else [normalize_theme_name(name)]
    try:
        for selected in names:
            configure_theme(selected)
            _preview_card(selected)
    finally:
        configure_theme(original)
    if len(names) == 1:
        next_steps([f"Save it globally: `scc theme use {names[0]}`.", f"Use once: `scc --theme {names[0]} <command>`."])


@theme_group.command("use")
@click.argument("name", required=False)
@click.option("--profile", "profile_name", default=None, help="Apply only to this connection profile.")
@click.pass_context
def use_theme(ctx: click.Context, name: Optional[str], profile_name: Optional[str]) -> None:
    """Select and persist a theme globally or for one connection profile."""
    if not name:
        if not click.get_text_stream("stdin").isatty():
            raise click.UsageError("NAME is required in non-interactive mode")
        name = click.prompt("Theme", type=click.Choice(list(PRESETS), case_sensitive=False), default=active_theme_name())
    selected = normalize_theme_name(name)
    _save_theme(ctx, selected, profile_name)
    configure_theme(selected)
    scope = f"profile '{profile_name}'" if profile_name else "global configuration"
    result_summary(
        f"{PRESETS[selected].label} theme selected",
        status="success",
        message=f"The theme was saved to {scope}.",
        details=[("Theme", selected), ("Scope", scope), ("Config file", _store(ctx).path)],
    )
    if selected == "plain":
        click.echo("Plain terminal output is now enabled. Use `scc theme enable` to restore enhanced presentation.")
    else:
        next_steps(["Preview the launch screen: `scc`.", "Review the effective source: `scc theme current`."])


@theme_group.command("disable")
@click.option("--profile", "profile_name", default=None, help="Disable themes only for this connection profile.")
@click.pass_context
def disable_theme(ctx: click.Context, profile_name: Optional[str]) -> None:
    """Disable colours, panels, decorative icons and animated presentation."""
    _save_theme(ctx, "plain", profile_name)
    configure_theme("plain")
    scope = f"profile '{profile_name}'" if profile_name else "global configuration"
    click.echo(f"Theme disabled for {scope}. SCC will use plain terminal output.")
    click.echo("Restore it with: scc theme enable")


@theme_group.command("enable")
@click.argument("name", required=False, default=DEFAULT_THEME)
@click.option("--profile", "profile_name", default=None, help="Enable the theme only for this connection profile.")
@click.pass_context
def enable_theme(ctx: click.Context, name: str, profile_name: Optional[str]) -> None:
    """Enable enhanced presentation using Ocean or another named theme."""
    selected = normalize_theme_name(name)
    if selected == "plain":
        raise click.UsageError("Use a professional theme name when enabling presentation")
    _save_theme(ctx, selected, profile_name)
    configure_theme(selected)
    scope = f"profile '{profile_name}'" if profile_name else "global configuration"
    result_summary(
        f"{PRESETS[selected].label} presentation enabled",
        status="success",
        message=f"The theme was saved to {scope}.",
    )


@theme_group.command("reset")
@click.option("--profile", "profile_name", default=None, help="Remove only this profile's theme override.")
@click.pass_context
def reset_theme(ctx: click.Context, profile_name: Optional[str]) -> None:
    """Reset the global theme or remove a profile-specific override."""
    store = _store(ctx)
    config = store.load()
    if profile_name:
        profile = config.profiles.get(profile_name)
        if profile is None:
            raise click.ClickException(f"Profile '{profile_name}' does not exist")
        config.profiles[profile_name] = profile.model_copy(update={"theme": None})
        effective = config.theme or DEFAULT_THEME
        scope = f"profile '{profile_name}' override"
    else:
        config.theme = DEFAULT_THEME
        effective = DEFAULT_THEME
        scope = "global theme"
    store.save(config)
    configure_theme(effective)
    result_summary(
        "Theme reset",
        status="success",
        message=f"Reset {scope}; effective theme is {effective}.",
    )
