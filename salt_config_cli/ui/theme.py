"""Runtime-selectable professional themes for Salt Config CLI.

Themes are semantic: the rest of the CLI refers to stable ``scc.*`` style
names, while this module swaps the palette at runtime.  ``plain`` mode turns
off colour and decorative Unicode icons for conventional terminal output.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.theme import Theme

DEFAULT_THEME = "ocean"


@dataclass(frozen=True)
class ThemePreset:
    name: str
    label: str
    description: str
    palette: dict[str, str]
    plain: bool = False


_COMMON_KEYS = (
    "scc.primary", "scc.secondary", "scc.accent", "scc.title", "scc.cmd", "scc.kbd",
    "scc.label", "scc.value", "scc.strong", "scc.hint", "scc.muted", "scc.success",
    "scc.success_dim", "scc.warning", "scc.danger", "scc.danger_dim", "scc.info",
    "scc.badge", "scc.error", "scc.subtitle", "scc.table.header", "scc.tree.guide",
    "scc.value.strong", "scc.metric.primary", "scc.metric.secondary", "scc.metric.accent",
    "scc.metric.success", "scc.metric.warning", "scc.metric.danger", "scc.metric.info",
    "scc.logo", "scc.logo.secondary", "scc.logo.accent", "scc.version",
)


def _palette(**values: str) -> dict[str, str]:
    missing = set(_COMMON_KEYS) - set(values)
    if missing:
        raise RuntimeError(f"Theme is missing semantic styles: {', '.join(sorted(missing))}")
    return values


PRESETS: dict[str, ThemePreset] = {
    "ocean": ThemePreset(
        "ocean", "Ocean", "Modern blue, violet and teal; closest to the original SCC demo.",
        _palette(
            **{
                "scc.primary": "bold #65b8ff", "scc.secondary": "bold #c792ea", "scc.accent": "bold #35e6b1",
                "scc.title": "bold #c792ea", "scc.cmd": "bold #35e6b1", "scc.kbd": "bold #35e6b1",
                "scc.label": "bold #a7b0c0", "scc.value": "#d5d9e2", "scc.strong": "bold #f0f3f8",
                "scc.hint": "italic #7e8797", "scc.muted": "#737b8c", "scc.success": "bold #35e66f",
                "scc.success_dim": "#68c987", "scc.warning": "bold #e6c75a", "scc.danger": "bold #ff6b7a",
                "scc.danger_dim": "#d57b84", "scc.info": "bold #65b8ff", "scc.badge": "bold black on #35e6b1",
                "scc.error": "bold #ff6b7a", "scc.subtitle": "#8f99aa", "scc.table.header": "bold #c792ea",
                "scc.tree.guide": "#556070", "scc.value.strong": "bold #f0f3f8",
                "scc.metric.primary": "black on #65b8ff", "scc.metric.secondary": "black on #c792ea",
                "scc.metric.accent": "black on #35e6b1", "scc.metric.success": "black on #35e66f",
                "scc.metric.warning": "black on #e6c75a", "scc.metric.danger": "white on #b54453",
                "scc.metric.info": "black on #65b8ff", "scc.logo": "bold #65b8ff",
                "scc.logo.secondary": "bold #c792ea", "scc.logo.accent": "bold #35e6b1",
                "scc.version": "black on #a7b0c0",
            }
        ),
    ),
    "enterprise": ThemePreset(
        "enterprise", "Enterprise", "Conservative navy, steel and emerald for production operations.",
        _palette(**{
            "scc.primary": "bold #4f8cc9", "scc.secondary": "bold #8ea6bf", "scc.accent": "bold #4db6a2",
            "scc.title": "bold #8ea6bf", "scc.cmd": "bold #72c7b7", "scc.kbd": "bold #72c7b7",
            "scc.label": "bold #9aa7b5", "scc.value": "#d6dde5", "scc.strong": "bold #f4f7fa",
            "scc.hint": "italic #7f8b98", "scc.muted": "#697684", "scc.success": "bold #59c98b",
            "scc.success_dim": "#78b998", "scc.warning": "bold #d8b45f", "scc.danger": "bold #e67878",
            "scc.danger_dim": "#bf7777", "scc.info": "bold #6fa7dc", "scc.badge": "bold white on #3f7c72",
            "scc.error": "bold #e67878", "scc.subtitle": "#8a98a6", "scc.table.header": "bold #9fb4c8",
            "scc.tree.guide": "#52606d", "scc.value.strong": "bold #f4f7fa",
            "scc.metric.primary": "white on #3f6f9e", "scc.metric.secondary": "white on #667c92",
            "scc.metric.accent": "black on #72c7b7", "scc.metric.success": "black on #59c98b",
            "scc.metric.warning": "black on #d8b45f", "scc.metric.danger": "white on #a94f4f",
            "scc.metric.info": "white on #4f8cc9", "scc.logo": "bold #4f8cc9",
            "scc.logo.secondary": "bold #8ea6bf", "scc.logo.accent": "bold #4db6a2",
            "scc.version": "white on #52606d",
        }),
    ),
    "graphite": ThemePreset(
        "graphite", "Graphite", "Neutral monochrome palette with restrained blue operational accents.",
        _palette(**{
            "scc.primary": "bold #b7c0cc", "scc.secondary": "bold #8f9aa8", "scc.accent": "bold #79a8d8",
            "scc.title": "bold #c5ccd5", "scc.cmd": "bold #8ab4df", "scc.kbd": "bold #8ab4df",
            "scc.label": "bold #9ca6b2", "scc.value": "#d4d8de", "scc.strong": "bold #f1f3f5",
            "scc.hint": "italic #7d8792", "scc.muted": "#69727d", "scc.success": "bold #83bd91",
            "scc.success_dim": "#779c80", "scc.warning": "bold #c8ad6d", "scc.danger": "bold #d78282",
            "scc.danger_dim": "#aa7474", "scc.info": "bold #79a8d8", "scc.badge": "bold black on #b7c0cc",
            "scc.error": "bold #d78282", "scc.subtitle": "#8d96a1", "scc.table.header": "bold #b7c0cc",
            "scc.tree.guide": "#59616b", "scc.value.strong": "bold #f1f3f5",
            "scc.metric.primary": "black on #b7c0cc", "scc.metric.secondary": "black on #8f9aa8",
            "scc.metric.accent": "black on #79a8d8", "scc.metric.success": "black on #83bd91",
            "scc.metric.warning": "black on #c8ad6d", "scc.metric.danger": "white on #985b5b",
            "scc.metric.info": "black on #79a8d8", "scc.logo": "bold #b7c0cc",
            "scc.logo.secondary": "bold #8f9aa8", "scc.logo.accent": "bold #79a8d8",
            "scc.version": "black on #9ca6b2",
        }),
    ),
    "forest": ThemePreset(
        "forest", "Forest", "Teal and green with muted gold accents for infrastructure workflows.",
        _palette(**{
            "scc.primary": "bold #55b8a9", "scc.secondary": "bold #8fbe78", "scc.accent": "bold #d2b66c",
            "scc.title": "bold #8fbe78", "scc.cmd": "bold #71c8b9", "scc.kbd": "bold #71c8b9",
            "scc.label": "bold #a5b5aa", "scc.value": "#d8e0db", "scc.strong": "bold #f1f7f3",
            "scc.hint": "italic #7d9185", "scc.muted": "#687b70", "scc.success": "bold #6fce8e",
            "scc.success_dim": "#79aa88", "scc.warning": "bold #d2b66c", "scc.danger": "bold #e17c76",
            "scc.danger_dim": "#b87570", "scc.info": "bold #67b7c9", "scc.badge": "bold black on #71c8b9",
            "scc.error": "bold #e17c76", "scc.subtitle": "#879b8f", "scc.table.header": "bold #8fbe78",
            "scc.tree.guide": "#52685c", "scc.value.strong": "bold #f1f7f3",
            "scc.metric.primary": "black on #55b8a9", "scc.metric.secondary": "black on #8fbe78",
            "scc.metric.accent": "black on #d2b66c", "scc.metric.success": "black on #6fce8e",
            "scc.metric.warning": "black on #d2b66c", "scc.metric.danger": "white on #a95752",
            "scc.metric.info": "black on #67b7c9", "scc.logo": "bold #55b8a9",
            "scc.logo.secondary": "bold #8fbe78", "scc.logo.accent": "bold #d2b66c",
            "scc.version": "black on #a5b5aa",
        }),
    ),
    "amber": ThemePreset(
        "amber", "Amber", "Warm amber and copper accents with cool blue informational states.",
        _palette(**{
            "scc.primary": "bold #e0a85b", "scc.secondary": "bold #c6865d", "scc.accent": "bold #67b7c9",
            "scc.title": "bold #e0a85b", "scc.cmd": "bold #79c4d3", "scc.kbd": "bold #79c4d3",
            "scc.label": "bold #b4aa9e", "scc.value": "#dfd9d2", "scc.strong": "bold #f7f3ee",
            "scc.hint": "italic #94887c", "scc.muted": "#786f67", "scc.success": "bold #78c58b",
            "scc.success_dim": "#79a686", "scc.warning": "bold #e0a85b", "scc.danger": "bold #e27070",
            "scc.danger_dim": "#b86e6e", "scc.info": "bold #67b7c9", "scc.badge": "bold black on #e0a85b",
            "scc.error": "bold #e27070", "scc.subtitle": "#9d9185", "scc.table.header": "bold #d69a62",
            "scc.tree.guide": "#61574f", "scc.value.strong": "bold #f7f3ee",
            "scc.metric.primary": "black on #e0a85b", "scc.metric.secondary": "black on #c6865d",
            "scc.metric.accent": "black on #67b7c9", "scc.metric.success": "black on #78c58b",
            "scc.metric.warning": "black on #e0a85b", "scc.metric.danger": "white on #a94f4f",
            "scc.metric.info": "black on #67b7c9", "scc.logo": "bold #e0a85b",
            "scc.logo.secondary": "bold #c6865d", "scc.logo.accent": "bold #67b7c9",
            "scc.version": "black on #b4aa9e",
        }),
    ),
    "high-contrast": ThemePreset(
        "high-contrast", "High Contrast", "Accessibility-oriented bright foregrounds and distinct status colours.",
        _palette(**{
            "scc.primary": "bold bright_cyan", "scc.secondary": "bold bright_magenta", "scc.accent": "bold bright_yellow",
            "scc.title": "bold bright_white", "scc.cmd": "bold bright_cyan", "scc.kbd": "bold bright_yellow",
            "scc.label": "bold white", "scc.value": "bright_white", "scc.strong": "bold bright_white",
            "scc.hint": "italic white", "scc.muted": "white", "scc.success": "bold bright_green",
            "scc.success_dim": "green", "scc.warning": "bold bright_yellow", "scc.danger": "bold bright_red",
            "scc.danger_dim": "red", "scc.info": "bold bright_cyan", "scc.badge": "bold black on bright_yellow",
            "scc.error": "bold bright_red", "scc.subtitle": "white", "scc.table.header": "bold bright_white",
            "scc.tree.guide": "white", "scc.value.strong": "bold bright_white",
            "scc.metric.primary": "black on bright_cyan", "scc.metric.secondary": "black on bright_magenta",
            "scc.metric.accent": "black on bright_yellow", "scc.metric.success": "black on bright_green",
            "scc.metric.warning": "black on bright_yellow", "scc.metric.danger": "bright_white on red",
            "scc.metric.info": "black on bright_cyan", "scc.logo": "bold bright_cyan",
            "scc.logo.secondary": "bold bright_magenta", "scc.logo.accent": "bold bright_yellow",
            "scc.version": "black on bright_white",
        }),
    ),
    "plain": ThemePreset(
        "plain", "Plain", "No colour, panels, decorative icons or animated terminal presentation.",
        _palette(**{key: "" for key in _COMMON_KEYS}),
        plain=True,
    ),
}

ALIASES = {
    "default": DEFAULT_THEME,
    "classic": DEFAULT_THEME,
    "none": "plain",
    "off": "plain",
    "disabled": "plain",
    "no-theme": "plain",
}


def normalize_theme_name(name: str | None) -> str:
    value = (name or DEFAULT_THEME).strip().lower().replace("_", "-")
    value = ALIASES.get(value, value)
    if value not in PRESETS:
        available = ", ".join(PRESETS)
        raise ValueError(f"Unknown theme '{name}'. Available themes: {available}")
    return value


THEMES: dict[str, Theme] = {name: Theme(preset.palette) for name, preset in PRESETS.items()}
THEME = THEMES[DEFAULT_THEME]  # compatibility export

_UNICODE_ICONS = {
    "success": "✓", "warning": "⚠", "error": "✗", "info": "●", "hint": "›", "arrow": "→",
    "rocket": "🚀", "magnify": "🔍", "doc": "📄", "folder": "📁", "environment": "🌐",
    "target": "🎯", "job": "⚙", "pillar": "◆", "minion": "♟", "gear": "⚙", "sparkle": "✨",
    "lock": "🔐", "server": "🔌", "plug": "🔌", "shield": "🛡", "user": "🔑",
    "workspace": "📂", "profile": "◉", "config": "☷", "switch": "⇄", "download": "↓",
    "upload": "↑", "running": "◆", "spinner": "◌", "fail": "✗", "warn": "⚠", "bullet": "•",
    "clock": "◷", "tree": "├", "theme": "◈",
}
_ASCII_ICONS = {
    "success": "OK", "warning": "WARN", "error": "ERROR", "info": "INFO", "hint": ">",
    "arrow": "->", "rocket": ">>", "magnify": "?", "doc": "file", "folder": "dir",
    "environment": "env", "target": "target", "job": "job", "pillar": "pillar", "minion": "minion",
    "gear": "*", "sparkle": "*", "lock": "auth", "server": "server", "plug": "server",
    "shield": "safe", "user": "user", "workspace": "workspace", "profile": "profile",
    "config": "config", "switch": "switch", "download": "get", "upload": "put", "running": "running",
    "spinner": "...", "fail": "ERROR", "warn": "WARN", "bullet": "-", "clock": "time",
    "tree": "+", "theme": "theme",
}


def _supports_unicode() -> bool:
    if os.getenv("SCC_ICONS", "auto").lower() == "none":
        return False
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        "✓⚠→🚀🔍📁".encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


ICONS: dict[str, str] = dict(_UNICODE_ICONS if _supports_unicode() else _ASCII_ICONS)
console = Console(theme=THEMES[DEFAULT_THEME], highlight=False, soft_wrap=False)
_ACTIVE_THEME = DEFAULT_THEME
_PUSHED_THEME = False


def configure_theme(name: str | None) -> str:
    """Activate a theme for the current process and return its canonical name."""
    global _ACTIVE_THEME, _PUSHED_THEME
    selected = normalize_theme_name(name)
    if _PUSHED_THEME:
        try:
            console.pop_theme()
        except Exception:
            pass
        _PUSHED_THEME = False
    if selected != DEFAULT_THEME:
        console.push_theme(THEMES[selected])
        _PUSHED_THEME = True
    preset = PRESETS[selected]
    console.no_color = bool(preset.plain or os.getenv("NO_COLOR"))
    use_unicode = _supports_unicode() and not preset.plain
    ICONS.clear()
    ICONS.update(_UNICODE_ICONS if use_unicode else _ASCII_ICONS)
    _ACTIVE_THEME = selected
    return selected


def active_theme_name() -> str:
    return _ACTIVE_THEME


def active_theme() -> Theme:
    return THEMES[_ACTIVE_THEME]


def is_plain() -> bool:
    return PRESETS[_ACTIVE_THEME].plain


def theme_choices() -> tuple[str, ...]:
    return tuple(PRESETS)


def theme_rows() -> list[tuple[str, str, str]]:
    return [(preset.name, preset.label, preset.description) for preset in PRESETS.values()]


def _argv_value(argv: list[str], option: str) -> str | None:
    for index, token in enumerate(argv):
        if token == option and index + 1 < len(argv):
            return argv[index + 1]
        if token.startswith(option + "="):
            return token.split("=", 1)[1]
    return None


def _discover_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    if os.getenv("SCC_CONFIG"):
        return Path(os.environ["SCC_CONFIG"]).expanduser()
    candidates = [
        Path.cwd() / ".scc" / "config.yaml", Path.cwd() / ".scc" / "config.yml",
        Path.home() / ".scc" / "config.yaml", Path.home() / ".scc" / "config.yml",
    ]
    return next((candidate for candidate in candidates if candidate.exists()), candidates[2])


def configured_theme(config_path: str | None = None, profile_name: str | None = None) -> str:
    """Resolve a persisted theme without importing the full settings layer."""
    path = _discover_path(config_path)
    if not path.exists():
        return DEFAULT_THEME
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return DEFAULT_THEME
    if not isinstance(raw, dict):
        return DEFAULT_THEME
    selected_profile = profile_name or os.getenv("SCC_PROFILE") or raw.get("default_profile") or "default"
    value: Any = raw.get("theme")
    profiles = raw.get("profiles")
    if isinstance(profiles, dict):
        profile = profiles.get(selected_profile)
        if isinstance(profile, dict) and profile.get("theme"):
            value = profile.get("theme")
    elif raw.get("theme"):
        value = raw.get("theme")
    try:
        return normalize_theme_name(str(value)) if value else DEFAULT_THEME
    except ValueError:
        return DEFAULT_THEME


def bootstrap_theme(
    *,
    cli_theme: str | None = None,
    config_path: str | None = None,
    profile_name: str | None = None,
    argv: list[str] | None = None,
) -> str:
    """Resolve and activate theme before help or command output is rendered."""
    args = list(sys.argv[1:] if argv is None else argv)
    explicit = cli_theme or _argv_value(args, "--theme") or os.getenv("SCC_THEME")
    cfg = config_path or _argv_value(args, "--config-file") or _argv_value(args, "--config")
    profile = profile_name or _argv_value(args, "--profile") or os.getenv("SCC_PROFILE")
    return configure_theme(explicit or configured_theme(cfg, profile))
