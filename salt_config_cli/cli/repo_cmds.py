"""Customer-friendly Git repository source management commands."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click

from salt_config_cli.core.repositories import (
    RepositoryConfigFile,
    RepositorySource,
    RepositoryStore,
    delete_source_token,
    export_non_secret_sources,
    get_source_token,
    set_source_token,
    source_env_token_name,
)
from salt_config_cli.services.git_repository import GitRepositoryError, GitRepositoryService
from salt_config_cli.ui import (
    RichGroup,
    command_header,
    data_table,
    empty_state,
    hint as ui_hint,
    kv_table,
    next_steps,
    prompt_password,
    result_summary,
    spinner,
    success as ui_success,
    warn as ui_warn,
)


def _root_config_path(ctx: click.Context) -> Optional[str]:
    root = ctx.find_root()
    return (root.obj or {}).get("config_path") if root.obj else None


def _store(
    ctx: click.Context,
    *,
    repository_file: Optional[str] = None,
    workspace: bool = False,
) -> RepositoryStore:
    return RepositoryStore(
        repository_file,
        connection_config=_root_config_path(ctx),
        workspace=workspace,
    )


def _load_token_from_input(*, token_stdin: bool, token_file: Optional[str]) -> str:
    if token_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    if token_file:
        path = Path(token_file).expanduser()
        value = path.read_text(encoding="utf-8").strip()
        if not value:
            raise click.ClickException(f"Token file is empty: {path}")
        return value
    if not sys.stdin.isatty():
        raise click.ClickException("Use --token-stdin or --token-file in non-interactive mode")
    return prompt_password("Git access token")


@click.group("repo", cls=RichGroup, invoke_without_command=True)
@click.pass_context
def repo_group(ctx: click.Context) -> None:
    """Manage reusable Salt-state and customer-values Git sources."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help(), nl=False)


@repo_group.command("setup")
@click.option("--workspace", is_flag=True, help="Save repository metadata in ./.scc/repositories.yaml.")
@click.option("--repository-file", type=click.Path(exists=False), help="Use another repository source file.")
@click.option("--non-interactive", is_flag=True, help="Do not prompt; use `repo add` instead.")
@click.pass_context
def repo_setup(ctx: click.Context, workspace: bool, repository_file: Optional[str], non_interactive: bool) -> None:
    """Guided setup for the public state repo and private customer-values repo."""
    command_header(
        "repo setup",
        "Configure Git content sources",
        description="Repository metadata is kept separate from RaaS profiles; credentials remain in Git/SSH/keychain.",
        icon="config",
    )
    if non_interactive or not sys.stdin.isatty():
        raise click.ClickException(
            "Guided setup needs an interactive terminal. Use `scc repo add <name> --kind ... --url ...`."
        )

    store = _store(ctx, repository_file=repository_file, workspace=workspace)
    document = store.load()
    if store.last_migration:
        ui_success(f"{store.last_migration}: {store.path}")

    states_name = click.prompt("Reusable Salt-state source name", default=document.default_states_source or "vcf-salt")
    existing_states = document.sources.get(states_name)
    states_url = click.prompt(
        "Reusable Salt-state Git URL",
        default=existing_states.url if existing_states else "",
        show_default=bool(existing_states),
    ).strip()
    if not states_url:
        raise click.ClickException("A Salt-state repository URL is required")
    states_ref = click.prompt("Approved branch, tag, or commit", default=existing_states.ref if existing_states else "main")
    states_root = click.prompt("Path containing resource folders", default=existing_states.root if existing_states else "vcf-infra")
    states_auth = click.prompt(
        "Authentication",
        type=click.Choice(["auto", "ssh", "credential-helper", "token"], case_sensitive=False),
        default=existing_states.auth if existing_states else "auto",
    )
    store.add(
        states_name,
        RepositorySource(
            kind="states",
            url=states_url,
            ref=states_ref,
            root=states_root,
            layout="{resource}",
            auth=states_auth,
            description="Reusable Salt states",
        ),
        make_default=True,
    )
    if states_auth == "token":
        ui_hint(
            f"Store the token securely with `scc repo login {states_name}` or set {source_env_token_name(states_name)}."
        )

    if click.confirm("Configure a separate customer-specific values repository?", default=True):
        refreshed = store.load()
        data_name = click.prompt("Customer-values source name", default=refreshed.default_data_source or "customer-values")
        existing_data = refreshed.sources.get(data_name)
        data_url = click.prompt(
            "Customer-values Git URL",
            default=existing_data.url if existing_data else "",
            show_default=bool(existing_data),
        ).strip()
        if data_url:
            data_ref = click.prompt("Approved branch, tag, or commit", default=existing_data.ref if existing_data else "main")
            data_root = click.prompt("Path containing environment/version values", default=existing_data.root if existing_data else ".")
            data_layout = click.prompt(
                "Values layout",
                default=existing_data.layout if existing_data and existing_data.layout else "{environment}/{version}/{resource}/values.yaml",
            )
            auth = click.prompt(
                "Authentication",
                type=click.Choice(["auto", "ssh", "credential-helper", "token"], case_sensitive=False),
                default=existing_data.auth if existing_data else "auto",
            )
            store.add(
                data_name,
                RepositorySource(
                    kind="data",
                    url=data_url,
                    ref=data_ref,
                    root=data_root,
                    layout=data_layout,
                    auth=auth,
                    description="Approved customer/environment-specific values",
                ),
                make_default=True,
            )
            if auth == "token":
                ui_hint(
                    f"Store the token securely with `scc repo login {data_name}` or set {source_env_token_name(data_name)}."
                )

    result_summary(
        "Repository sources configured",
        details=[("Source file", str(store.path)), ("Secrets stored", "No")],
    )
    next_steps(
        [
            "Verify access: `scc repo test --all`",
            "Preview a deployment: `scc deploy <resource> --environment <env> --version <version>`",
            "Open the simple walkthrough: `scc tutorial gitops`",
        ]
    )


@repo_group.command("add")
@click.argument("name")
@click.option("--kind", type=click.Choice(["states", "data"]), required=True, help="Type of content in this source.")
@click.option("--url", required=True, help="Generic Git URL: HTTPS, SSH, file://, or a local path.")
@click.option("--ref", default="main", show_default=True, help="Approved branch, tag, or immutable commit SHA.")
@click.option("--root", default=".", show_default=True, help="Relative path inside the repository.")
@click.option("--layout", help="Resource path template using {resource}, {environment}, {version}, or {values}.")
@click.option("--auth", type=click.Choice(["auto", "ssh", "credential-helper", "token"]), default="auto", show_default=True)
@click.option("--username", help="Username used only with token authentication.")
@click.option("--verify-tls/--no-verify-tls", default=True, show_default=True)
@click.option("--description")
@click.option("--default", "make_default", is_flag=True, help="Make this the default source for its kind.")
@click.option("--workspace", is_flag=True, help="Save in ./.scc/repositories.yaml.")
@click.option("--repository-file", type=click.Path(exists=False), help="Use another repository source file.")
@click.pass_context
def repo_add(
    ctx: click.Context,
    name: str,
    kind: str,
    url: str,
    ref: str,
    root: str,
    layout: Optional[str],
    auth: str,
    username: Optional[str],
    verify_tls: bool,
    description: Optional[str],
    make_default: bool,
    workspace: bool,
    repository_file: Optional[str],
) -> None:
    """Add or update a non-secret Git source."""
    if not layout:
        layout = "{resource}" if kind == "states" else None
    store = _store(ctx, repository_file=repository_file, workspace=workspace)
    source = RepositorySource(
        kind=kind,
        url=url,
        ref=ref,
        root=root,
        layout=layout,
        auth=auth,
        username=username,
        verify_tls=verify_tls,
        description=description,
    )
    store.add(name, source, make_default=make_default)
    result_summary(
        f"Repository source '{name}' saved",
        details=[
            ("Kind", kind),
            ("Repository", url),
            ("Ref", ref),
            ("Root", root),
            ("Layout", layout or "automatic discovery"),
            ("Auth", auth),
            ("Source file", str(store.path)),
        ],
    )
    if auth == "token":
        ui_hint(f"Credentials were not saved. Run `scc repo login {name}` or set {source_env_token_name(name)}.")
    if not verify_tls:
        ui_warn("TLS verification is disabled for this source. Use a trusted CA and enable verification for production.")
    next_steps([f"Test access: `scc repo test {name}`", "List all sources: `scc repo list`"])


@repo_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--repository-file", type=click.Path(exists=False))
@click.pass_context
def repo_list(ctx: click.Context, as_json: bool, repository_file: Optional[str]) -> None:
    """List configured Git sources and defaults."""
    store = _store(ctx, repository_file=repository_file)
    document = store.load()
    if as_json:
        click.echo(json.dumps(document.model_dump(mode="json", exclude_none=True), indent=2))
        return
    command_header(
        "repo list",
        "Git content sources",
        description="Reusable states and customer values are versioned independently and contain no stored secrets.",
        icon="doc",
        meta=[("Source file", str(store.path))],
    )
    if store.last_migration:
        ui_success(store.last_migration)
    if not document.sources:
        empty_state(
            "No Git sources configured",
            "Start with a guided setup; SCC keeps these settings outside the RaaS profile file.",
            icon="config",
            actions=["scc repo setup", "scc repo add vcf-salt --kind states --url <url> --root vcf-infra --default"],
        )
        return
    rows = []
    for name, source in sorted(document.sources.items()):
        default = (
            name == document.default_states_source if source.kind == "states" else name == document.default_data_source
        )
        token, credential_source = (
            get_source_token(name, kind=source.kind) if source.auth == "token" else (None, "")
        )
        auth_status = {
            "auto": "Git/SSH auto",
            "ssh": "SSH agent/key",
            "credential-helper": "Git helper",
        }.get(source.auth, credential_source if token else "missing")
        rows.append(
            [
                name,
                source.kind,
                "default" if default else "",
                source.ref,
                source.root,
                source.auth,
                auth_status,
                source.url,
            ]
        )
    data_table(
        f"Repository sources ({len(rows)})",
        [
            ("Name", "scc.strong"),
            ("Kind", "scc.secondary"),
            ("Default", "scc.success"),
            ("Ref", "scc.accent"),
            ("Root", "scc.value"),
            ("Auth", "scc.value"),
            ("Credential", "scc.muted"),
            ("URL", "scc.value"),
        ],
        rows,
        icon="doc",
        caption="Use an approved tag or commit SHA for reproducible production deployments.",
    )


@repo_group.command("show")
@click.argument("name")
@click.option("--repository-file", type=click.Path(exists=False))
@click.pass_context
def repo_show(ctx: click.Context, name: str, repository_file: Optional[str]) -> None:
    """Show one source without exposing credentials."""
    store = _store(ctx, repository_file=repository_file)
    selected, source = store.get(name)
    token, credential_source = (
        get_source_token(selected, kind=source.kind) if source.auth == "token" else (None, "")
    )
    auth_status = {
        "auto": "Git credential helper or SSH agent",
        "ssh": "SSH agent/key",
        "credential-helper": "Git credential helper",
    }.get(source.auth, credential_source if token else "missing")
    kv_table(
        f"Repository source: {selected}",
        [
            ("Kind", source.kind),
            ("URL", source.url),
            ("Ref", source.ref),
            ("Root", source.root),
            ("Layout", source.layout or "automatic"),
            ("Authentication", source.auth),
            ("Credential", auth_status),
            ("TLS verification", "enabled" if source.verify_tls else "disabled"),
            ("Description", source.description or "-"),
            ("Source file", str(store.path)),
        ],
    )


@repo_group.command("use")
@click.argument("name")
@click.option("--repository-file", type=click.Path(exists=False))
@click.pass_context
def repo_use(ctx: click.Context, name: str, repository_file: Optional[str]) -> None:
    """Make a source the default for its kind."""
    store = _store(ctx, repository_file=repository_file)
    store.set_default(name)
    _, source = store.get(name)
    ui_success(f"'{name}' is now the default {source.kind} source")


@repo_group.command("test")
@click.argument("name", required=False)
@click.option("--all", "all_sources", is_flag=True, help="Test every configured source.")
@click.option("--repository-file", type=click.Path(exists=False))
@click.pass_context
def repo_test(ctx: click.Context, name: Optional[str], all_sources: bool, repository_file: Optional[str]) -> None:
    """Authenticate, fetch the configured ref, and report its commit."""
    store = _store(ctx, repository_file=repository_file)
    document = store.load()
    if all_sources:
        names = list(sorted(document.sources))
    elif name:
        names = [name]
    else:
        names = [value for value in (document.default_states_source, document.default_data_source) if value]
    if not names:
        raise click.ClickException("No repository sources are configured. Run `scc repo setup`.")

    service = GitRepositoryService()
    rows = []
    failed = 0
    for source_name in names:
        source = document.sources.get(source_name)
        if not source:
            failed += 1
            rows.append([source_name, "missing", "-", "-", "Source does not exist"])
            continue
        try:
            with spinner(f"Testing {source_name}@{source.ref}…"):
                synced = service.test(source_name, source)
            rows.append([source_name, "ready", source.kind, synced.commit[:12], synced.committed_at])
        except GitRepositoryError as exc:
            failed += 1
            rows.append([source_name, "failed", source.kind, "-", str(exc)])
    data_table(
        "Repository access test",
        [
            ("Source", "scc.strong"),
            ("Status", "scc.secondary"),
            ("Kind", "scc.value"),
            ("Commit", "scc.accent"),
            ("Details", "scc.value"),
        ],
        rows,
        icon="shield",
    )
    if failed:
        raise click.ClickException(f"{failed} repository source(s) failed")
    ui_success("All requested repository sources are ready")


@repo_group.command("sync")
@click.argument("name", required=False)
@click.option("--all", "all_sources", is_flag=True)
@click.option("--repository-file", type=click.Path(exists=False))
@click.pass_context
def repo_sync(ctx: click.Context, name: Optional[str], all_sources: bool, repository_file: Optional[str]) -> None:
    """Refresh the private shallow cache used by deployment workflows."""
    ctx.invoke(repo_test, name=name, all_sources=all_sources, repository_file=repository_file)


@repo_group.command("login")
@click.argument("name")
@click.option("--token-stdin", is_flag=True, help="Read the token from stdin.")
@click.option("--token-file", type=click.Path(exists=True, dir_okay=False), help="Read the token from a 0600 file.")
@click.option("--repository-file", type=click.Path(exists=False))
@click.pass_context
def repo_login(
    ctx: click.Context,
    name: str,
    token_stdin: bool,
    token_file: Optional[str],
    repository_file: Optional[str],
) -> None:
    """Store a private-repository token in the OS keychain, never YAML."""
    store = _store(ctx, repository_file=repository_file)
    _, source = store.get(name)
    token = _load_token_from_input(token_stdin=token_stdin, token_file=token_file)
    if not token:
        raise click.ClickException("Token cannot be empty")
    if not set_source_token(name, token):
        raise click.ClickException(
            f"No writable OS keychain is available. Set {source_env_token_name(name)} for this source instead."
        )
    ui_success(f"Credential stored securely for '{name}'")
    if source.auth != "token":
        ui_warn(f"Source auth mode is '{source.auth}'. Change it with `scc repo add ... --auth token` if needed.")


@repo_group.command("logout")
@click.argument("name")
@click.option("--repository-file", type=click.Path(exists=False))
@click.pass_context
def repo_logout(ctx: click.Context, name: str, repository_file: Optional[str]) -> None:
    """Remove a repository token from the OS keychain."""
    store = _store(ctx, repository_file=repository_file)
    store.get(name)
    if delete_source_token(name):
        ui_success(f"Stored credential removed for '{name}'")
    else:
        ui_warn("No keychain credential was found or the keychain is unavailable")


@repo_group.command("remove")
@click.argument("name")
@click.option("--yes", is_flag=True)
@click.option("--repository-file", type=click.Path(exists=False))
@click.pass_context
def repo_remove(ctx: click.Context, name: str, yes: bool, repository_file: Optional[str]) -> None:
    """Delete non-secret source metadata and optionally its keychain token."""
    store = _store(ctx, repository_file=repository_file)
    store.get(name)
    if not yes and not click.confirm(f"Remove repository source '{name}'?", default=False):
        ui_warn("Repository source removal cancelled")
        return
    store.remove(name)
    delete_source_token(name)
    ui_success(f"Repository source '{name}' removed")


@repo_group.command("path")
@click.option("--repository-file", type=click.Path(exists=False))
@click.pass_context
def repo_path(ctx: click.Context, repository_file: Optional[str]) -> None:
    """Print the active repository source file path."""
    click.echo(_store(ctx, repository_file=repository_file).path)


@repo_group.command("export")
@click.option("--output", type=click.Path(dir_okay=False), help="Write to a file instead of stdout.")
@click.option("--repository-file", type=click.Path(exists=False))
@click.pass_context
def repo_export(ctx: click.Context, output: Optional[str], repository_file: Optional[str]) -> None:
    """Export non-secret source metadata for review or onboarding."""
    store = _store(ctx, repository_file=repository_file)
    text = export_non_secret_sources(store.load())
    if output:
        destination = Path(output).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        try:
            os.chmod(destination, 0o600)
        except OSError:
            pass
        ui_success(f"Repository metadata exported to {destination}")
    else:
        click.echo(text, nl=False)


@repo_group.command("import")
@click.argument("file", type=click.Path(exists=True, dir_okay=False))
@click.option("--replace", is_flag=True, help="Replace the current catalog instead of merging sources.")
@click.option("--yes", is_flag=True, help="Skip the replacement confirmation.")
@click.option("--repository-file", type=click.Path(exists=False))
@click.pass_context
def repo_import(
    ctx: click.Context,
    file: str,
    replace: bool,
    yes: bool,
    repository_file: Optional[str],
) -> None:
    """Import reviewed non-secret repository metadata from YAML."""
    import yaml
    from pydantic import ValidationError

    source_path = Path(file).expanduser()
    try:
        raw = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
        imported = RepositoryConfigFile.model_validate(raw)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as exc:
        raise click.ClickException(f"Unable to import repository metadata from {source_path}: {exc}") from exc

    store = _store(ctx, repository_file=repository_file)
    current = store.load()
    if replace:
        if current.sources and not yes and not click.confirm(
            f"Replace {len(current.sources)} existing source(s) with {len(imported.sources)} imported source(s)?",
            default=False,
        ):
            ui_warn("Repository import cancelled")
            return
        merged = imported
    else:
        merged = current.model_copy(deep=True)
        merged.sources.update(imported.sources)
        if imported.default_states_source:
            merged.default_states_source = imported.default_states_source
        if imported.default_data_source:
            merged.default_data_source = imported.default_data_source
    store.save(merged)
    result_summary(
        "Repository metadata imported",
        details=[
            ("Input", str(source_path)),
            ("Destination", str(store.path)),
            ("Mode", "replace" if replace else "merge"),
            ("Sources", len(merged.sources)),
            ("Credentials imported", "No"),
        ],
    )
    next_steps(["Verify access: `scc repo test --all`", "Review sources: `scc repo list`"])


def register(group: click.Group) -> None:
    group.add_command(repo_group)
